"""Runs the Photos-slot writer's real Thumb code in the Unicorn emulator.

The firmware functions it calls (operator new, file open/seek/write, the file
object's vtable close) are replaced by Python hooks that record what's written.
The output is compared against a numpy reference of the same conversion.

    python tests/emulate_photos_slot.py firmware/yuv/PIC_0027.yuv [photo number] [out dir] [slots] [next number] [UI angle]
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

import numpy as np
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
                               UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "patches"))
import photos_slot as ps  # noqa: E402

FRAME = 0x20000000
PATH = 0x21000000
STACK = 0x22000000
HEAP = 0x23000000
VTABLE = 0x24000000
STOP = 0x25000000
UI_OBJ = 0x26000000


# angle -> (flip, landscape, EXIF orientation byte written, or None if the JPEG is left alone)
ANGLES = {0: (False, False, None), 180: (True, False, 8), 90: (False, True, 1), 270: (True, True, 3)}


def reference(frame: np.ndarray, angle: int = 0):
    """numpy version of the same integer conversion."""
    flip, land, _ = ANGLES[angle]
    q = frame.reshape(480, 640 * 2)

    def pix(x, y):
        if flip:
            x, y = 639 - x, 479 - y
        o = (y * 640 + x) * 2
        Y = int(q.flat[o]); g = o & ~3
        u = int(q.flat[g + 1]) - 128; v = int(q.flat[g + 3]) - 128
        r = Y + ((359 * v) >> 8); gg = Y - ((88 * u + 183 * v) >> 8); b = Y + ((454 * u) >> 8)
        r, gg, b = (min(255, max(0, c)) for c in (r, gg, b))
        return ((r >> 3) << 11) | ((gg >> 2) << 5) | (b >> 3)

    big = np.zeros((384, 384), np.uint16)
    small = np.zeros((64, 64), np.uint16)
    if not land:
        for oy in range(384):
            rx = (oy * 1707) >> 10
            for ox in range(288):
                big[oy, 48 + ox] = pix(rx, 479 - ((ox * 1707) >> 10))
        for oy in range(64):
            rx = 80 + ((15 * oy) >> 1)
            for ox in range(64):
                small[oy, ox] = pix(rx, 479 - ((15 * ox) >> 1))
    else:
        for oy in range(ps.LAND_TOP, ps.LAND_TOP + ps.LAND_H):
            ry = ((oy - ps.LAND_TOP) * 2276) >> 10
            for ox in range(288):
                big[oy, 48 + ox] = pix((ox * 2276) >> 10, ry)
        for oy in range(64):
            ry = (15 * oy) >> 1
            for ox in range(64):
                small[oy, ox] = pix(80 + ((15 * ox) >> 1), ry)
    return big, small


def main() -> int:
    yuv = Path(sys.argv[1])
    number = int(sys.argv[2]) if len(sys.argv) > 2 else 27
    slots = int(sys.argv[4]) if len(sys.argv) > 4 else 10
    next_number = int(sys.argv[5]) if len(sys.argv) > 5 else 0
    angle = int(sys.argv[6]) if len(sys.argv) > 6 else 0          # UI rotation in degrees
    offset = ps.default_offset(slots, next_number)
    raw = np.fromfile(yuv, np.uint8).reshape(-1, 2)[:, ::-1].reshape(-1)   # file is UYVY -> memory YUYV
    pcode, pl, wcode, wl, hcode, hl, ecode, el, scode, sl = ps.build(slots, offset)

    mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    for base, size in ((0x08000000, 0x700000), (FRAME, 0x100000), (PATH, 0x1000), (STACK - 0x10000, 0x20000),
                       (HEAP, 0x10000), (VTABLE, 0x1000), (STOP, 0x1000), (UI_OBJ, 0x1000)):
        mu.mem_map(base, size)
    for base, code in ((ps.REGION_A[0], wcode), (ps.REGION_B[0], pcode), (ps.REGION_C[0], hcode),
                       (ps.REGION_D[0], ecode), (ps.REGION_E[0], scode)):
        mu.mem_write(base, code)
    mu.mem_write(FRAME, raw.tobytes())
    mu.mem_write(PATH, f"/DCIM/000APPLE/PIC_{number:04d}.jpg\0".encode())
    mu.mem_write(VTABLE, struct.pack("<II", 0, VTABLE + 0x100 | 1))      # vtable[1] = close stub
    mu.mem_write(UI_OBJ + ps.ROTATION_AT, struct.pack("<I", angle))

    files = {}           # handle -> dict(path, pos, data)
    state = {"heap": HEAP, "next": 1}
    log = []

    def ret(value=None):
        if value is not None:
            mu.reg_write(UC_ARM_REG_R0, value)
        mu.reg_write(UC_ARM_REG_PC, mu.reg_read(UC_ARM_REG_LR))

    def cstr(a):
        out = b""
        while (c := mu.mem_read(a, 1)) != b"\0":
            out += c; a += 1
        return out.decode()

    def hook(uc, addr, size, user):
        a = addr & ~1
        r = [uc.reg_read(x) for x in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)]
        sp = uc.reg_read(UC_ARM_REG_SP)
        if a == ps.UI_SYSTEM:
            ret(UI_OBJ)
        elif a == ps.OP_NEW:
            p = state["heap"]; state["heap"] += (r[0] + 15) & ~15; ret(p)
        elif a == ps.FILE_OPEN:
            obj = r[0]; uc.mem_write(obj, struct.pack("<I", VTABLE))
            args = struct.unpack("<III", uc.mem_read(sp, 12))
            files[obj] = {"path": cstr(r[1]), "pos": 0, "data": {}}
            log.append(f"open {files[obj]['path']} ro={r[2]} r3={r[3]} stack={args}")
            ret(obj)
        elif a == ps.FILE_SEEK:
            whence = struct.unpack("<I", uc.mem_read(sp, 4))[0]
            files[r[0]]["pos"] = r[2] | (r[3] << 32)
            log.append(f"seek {files[r[0]]['pos']:#x} whence={whence}")
            ret(0)
        elif a == ps.FILE_WRITE:
            f = files[r[0]]; f["data"][f["pos"]] = bytes(uc.mem_read(r[2], r[1])); f["pos"] += r[1]
            uc.mem_write(r[3], struct.pack("<I", r[1])); ret(0)
        elif a == VTABLE + 0x100:
            log.append(f"close {files[r[0]]['path']}"); ret()
        elif a == STOP:
            uc.emu_stop()

    mu.hook_add(UC_HOOK_CODE, hook)
    sp = STACK
    mu.reg_write(UC_ARM_REG_SP, sp)
    mu.reg_write(UC_ARM_REG_R0, PATH)
    mu.reg_write(UC_ARM_REG_R1, FRAME)
    mu.reg_write(UC_ARM_REG_LR, STOP | 1)
    mu.emu_start(wl["WRITE_SLOTS"] | 1, STOP)
    assert mu.reg_read(UC_ARM_REG_SP) == sp, "stack not balanced"

    for line in log[:3] + ["..."] + log[-3:]:
        print(" ", line)
    _, _, exif_value = ANGLES[angle]
    big_ref, small_ref = reference(raw, angle)
    slot = (number + offset) % slots
    out = {}
    files_raw = {}
    for f in files.values():
        blob = b"".join(v for k, v in sorted(f["data"].items()))
        start = min(f["data"])
        files_raw[f["path"]] = blob
        out[f["path"]] = (start, np.frombuffer(blob, "<u2") if len(blob) % 2 == 0 else None)
    jpg_path = f"/DCIM/000APPLE/PIC_{number:04d}.jpg"
    exif = out.pop(jpg_path, None)
    if exif_value is None:
        ok_exif = exif is None                       # the JPEG is never opened
    else:                                            # one byte, written at offset 55
        ok_exif = exif is not None and exif[0] == 55 and files_raw[jpg_path] == bytes([exif_value])
    s87, b87 = out["/Photos/Thumbs/F1087_1.ithmb"]
    s66, b66 = out["/Photos/Thumbs/F1066_1.ithmb"]
    ok87 = s87 == slot * 0x48000 and np.array_equal(b87.reshape(384, 384), big_ref)
    ok66 = s66 == slot * 0x2000 and np.array_equal(b66.reshape(64, 64), small_ref)
    print(f"angle {angle}: slot {slot}: F1087 at {s87:#x} {'MATCH' if ok87 else 'MISMATCH'}; "
          f"F1066 at {s66:#x} {'MATCH' if ok66 else 'MISMATCH'}; "
          f"EXIF {'untouched' if exif_value is None else f'set to {exif_value}'}: {'OK' if ok_exif else 'WRONG'}")

    from PIL import Image
    def to_img(a):
        a = a.astype(np.uint32)
        rgb = np.stack([((a >> 11) & 31) << 3, ((a >> 5) & 63) << 2, (a & 31) << 3], -1).astype(np.uint8)
        return Image.fromarray(rgb)
    outdir = Path(sys.argv[3]) if len(sys.argv) > 3 else ROOT
    to_img(b87.reshape(384, 384)).save(outdir / "emu_F1087.png")
    to_img(b66.reshape(64, 64)).resize((256, 256), Image.NEAREST).save(outdir / "emu_F1066.png")
    return 0 if ok87 and ok66 and ok_exif else 1


if __name__ == "__main__":
    sys.exit(main())
