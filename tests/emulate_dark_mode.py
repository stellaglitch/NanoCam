"""Runs the patched resource getter (FUN_081a3f86 + the Dark Mode hook) in the Unicorn emulator.

The real firmware image is mapped, so the getter, the hook and its tables are the bytes
that would run on the iPod. Two things are faked: the resource manager (its vtable[0x74]
is a Python hook that answers from the real resource database) and the preferences object
(its vtable[0x4c] returns the Dark Mode setting we choose).

    python tests/emulate_dark_mode.py [firmware/n5g-retailos.dec]
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_R4,
                               UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7, UC_ARM_REG_SP, UC_ARM_REG_LR,
                               UC_ARM_REG_PC)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "patches"))
import dark_mode_toggle as dt  # noqa: E402
from nanocam.img1 import Img1  # noqa: E402
from nanocam.patch import apply  # noqa: E402
from nanocam.resources import ResourceDB  # noqa: E402

IMAGE = 0x07FD1000                     # page holding dt.BASE
FAKE = 0x20000000                      # manager, prefs and their vtables
STACK = 0x22000000
MGR, MGR_VT, PREFS, PREFS_VT = FAKE, FAKE + 0x100, FAKE + 0x400, FAKE + 0x500
MGR_FIND, PREFS_GET, STOP = FAKE + 0x800, FAKE + 0x900, FAKE + 0xA00
LIGHT = [b for lo, hi, _, _ in dt.BITMAP_RANGES for b in range(lo, hi + 1)]
ALL_BITMAPS = LIGHT + sorted({dt.dark_bitmap(b) for b in LIGHT}) + [0x0DAD0567, 0x0DAD0142, 0x0DAD0175, 0x0000A766]
CALLEE_SAVED = (UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7)


class Machine:
    def __init__(self, body: bytes):
        self.body = body
        self.db = ResourceDB(body)
        self.dark = False
        self.prefs_exist = True
        self.key_seen = None
        mu = self.mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
        mu.mem_map(IMAGE, (len(body) + (dt.BASE - IMAGE) + 0xFFF) & ~0xFFF)
        mu.mem_write(dt.BASE, body)
        mu.mem_map(FAKE, 0x4000)
        mu.mem_map(STACK - 0x10000, 0x10000)
        mu.mem_write(MGR, struct.pack("<I", MGR_VT) + bytes(0x10) + struct.pack("<I", 0))   # [+0x14] next = 0
        mu.mem_write(MGR_VT + 0x74, struct.pack("<I", MGR_FIND | 1))
        mu.mem_write(PREFS, struct.pack("<I", PREFS_VT))
        mu.mem_write(PREFS_VT + dt.PREFS_GET_BOOL, struct.pack("<I", PREFS_GET | 1))
        for stub in (MGR_FIND, PREFS_GET, STOP, dt.GET_MANAGER):
            mu.mem_write(stub, bytes.fromhex("7047"))    # bx lr
        mu.hook_add(UC_HOOK_CODE, lambda mu, *a: mu.reg_write(UC_ARM_REG_R0, MGR),
                    begin=dt.GET_MANAGER, end=dt.GET_MANAGER)
        # fake bitmap cache objects: 0x20 bytes each, the bitmap's id as the first word
        self.bitmaps = {}
        for i, bid in enumerate(ALL_BITMAPS):
            self.bitmaps[bid] = FAKE + 0xB00 + i * 0x20
            mu.mem_write(self.bitmaps[bid], struct.pack("<I", bid))
        mu.hook_add(UC_HOOK_CODE, self._find, begin=MGR_FIND, end=MGR_FIND)
        mu.hook_add(UC_HOOK_CODE, self._get_bool, begin=PREFS_GET, end=PREFS_GET)

    def _find(self, mu, addr, size, user):
        """vtable[0x74](manager, type, id, &out) -> found"""
        rtype = struct.pack(">I", mu.reg_read(UC_ARM_REG_R1)).decode("latin1")
        rid = mu.reg_read(UC_ARM_REG_R2)
        if rtype == "BMap":      # bitmaps aren't in the firmware: hand out fake cache objects
            ptr = self.bitmaps.get(rid)
        else:
            res = self.db.get(rtype, rid)
            ptr = res.offset + dt.BASE if res else None
        if ptr:
            mu.mem_write(mu.reg_read(UC_ARM_REG_R3), struct.pack("<I", ptr))
        mu.reg_write(UC_ARM_REG_R0, 1 if ptr else 0)
        for r in (UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3):      # caller-saved: trash them
            mu.reg_write(r, 0xDEADBEEF)

    def _get_bool(self, mu, addr, size, user):
        """vtable[0x4c](prefs, key, u8 *out)"""
        key = mu.reg_read(UC_ARM_REG_R1)
        self.key_seen = bytes(mu.mem_read(key, 32)).split(b"\0")[0].decode()
        mu.mem_write(mu.reg_read(UC_ARM_REG_R2), bytes([1 if self.dark else 0]))
        for r in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3):
            mu.reg_write(r, 0xDEADBEEF)

    def get(self, rtype: str, rid: int, ret: int = STOP) -> bytes | None:
        """Call FUN_081a3f86(manager, type, id) and return the 4 bytes it points at."""
        mu = self.mu
        mu.mem_write(dt.PREFS_SLOT, struct.pack("<I", PREFS if self.prefs_exist else 0))
        saved = [0x1111 * (i + 4) for i in range(4)]
        for reg, v in zip(CALLEE_SAVED, saved):
            mu.reg_write(reg, v)
        mu.reg_write(UC_ARM_REG_R0, MGR)
        mu.reg_write(UC_ARM_REG_R1, struct.unpack(">I", rtype.encode("latin1"))[0])
        mu.reg_write(UC_ARM_REG_R2, rid)
        mu.reg_write(UC_ARM_REG_SP, STACK - 0x100)
        mu.reg_write(UC_ARM_REG_LR, ret | 1)          # `ret`: pretend to be that call site
        mu.emu_start(dt.GET_RESOURCE | 1, ret, count=10000)
        assert mu.reg_read(UC_ARM_REG_PC) == ret, f"didn't return (pc = {mu.reg_read(UC_ARM_REG_PC):#x})"
        assert mu.reg_read(UC_ARM_REG_SP) == STACK - 0x100, "stack not balanced"
        assert [mu.reg_read(r) for r in CALLEE_SAVED] == saved, "callee-saved registers changed"
        ptr = mu.reg_read(UC_ARM_REG_R0)
        if ptr == 0:
            return None
        assert ptr % 4 == 0, "colour pointer must be word-aligned (callers use ldr)"
        return bytes(mu.mem_read(ptr, 4))


def _table_colour(self, colour: bytes) -> bytes:
    """Run the patched instructions of the table's draw method (0x08058102..0x08058108) on a fake
    table object and return the 4 colour bytes r1 ends up pointing at."""
    mu = self.mu
    obj = FAKE + 0x3000
    mu.mem_write(dt.PREFS_SLOT, struct.pack("<I", PREFS if self.prefs_exist else 0))
    mu.mem_write(obj + 0x170, colour)
    regs = {UC_ARM_REG_R7: obj, UC_ARM_REG_R2: 0x2222, UC_ARM_REG_R3: 0x3333, UC_ARM_REG_R4: 0x4444}
    for r, v in regs.items():
        mu.reg_write(r, v)
    mu.reg_write(UC_ARM_REG_SP, STACK - 0x100)
    start = dt.TABLE_DRAW_COLOUR - 2            # mov r1, r7
    mu.emu_start(start | 1, dt.TABLE_DRAW_COLOUR + 4, count=10000)
    assert mu.reg_read(UC_ARM_REG_PC) == dt.TABLE_DRAW_COLOUR + 4, "table draw hook didn't return"
    assert mu.reg_read(UC_ARM_REG_SP) == STACK - 0x100, "table draw hook: stack not balanced"
    assert all(mu.reg_read(r) == v for r, v in regs.items()), "table draw hook changed r2-r4/r7"
    return bytes(mu.mem_read(mu.reg_read(UC_ARM_REG_R1), 4))


Machine.table_colour = _table_colour


def main() -> int:
    src = sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "firmware" / "n5g-retailos.dec")
    stock = Img1.parse(Path(src).read_bytes()).body
    db = ResourceDB(stock)
    m = Machine(apply(stock, dt.build_patches(stock)))
    colours = {r.id: r.data(stock) for r in db.by_type["COLR"]}
    dark = {cid: bytes.fromhex(v) for cid, v in dt.COLOR_MAP.items()}
    others = [("Str ", 0x0DAD0E31), ("SORC", 0x985), ("View", 0x0DAD14BD), ("CLov", 0x0DAD11B5)]

    def check(label: str, expect: dict[int, bytes]):
        for cid, want in expect.items():
            got = m.get("COLR", cid)
            assert got == want, f"{label}: COLR {cid:#x} = {got and got.hex()}, expected {want.hex()}"
        for rtype, rid in others:      # other types must never be touched (ids can collide with colours)
            res = m.db.get(rtype, rid)
            assert m.get(rtype, rid) == res.data(m.body)[:4], f"{label}: {rtype} {rid:#x} changed"
        assert m.get("COLR", 0x0DAD0000) is None and m.get("COLR", 0x12345678) is None, f"{label}: missing id"
        swapped = 0
        for bid in m.bitmaps:    # each lookup returns a bitmap object; its first word says which one
            want = dt.dark_bitmap(bid) if dark_bitmaps and bid in LIGHT and dt.dark_bitmap(bid) in m.bitmaps else bid
            got = struct.unpack("<I", m.get("BMap", bid))[0]
            assert got == want, f"{label}: bitmap {bid:#x} gave {got:#x}, expected {want:#x}"
            swapped += got != bid
        assert m.get("BMap", 0x0DAD9999) is None, f"{label}: missing bitmap"
        assert m.get("COLR", 0) is None and m.get("BMap", 0) is None, f"{label}: id 0"
        # the menu table's draw: opaque white becomes the dark background only while Dark Mode is on
        rgba = bytes.fromhex(dt.DARK_BACKGROUND)
        dark_bg = bytes([rgba[2], rgba[1], rgba[0], rgba[3]])
        white = b"\xff" * 4
        assert m.table_colour(white) == (dark_bg if m.dark and m.prefs_exist else white), f"{label}: table background"
        assert m.table_colour(b"\x10\x20\x30\xff") == b"\x10\x20\x30\xff", f"{label}: coloured table"
        assert m.table_colour(b"\xff\xff\xff\x00") == b"\xff\xff\xff\x00", f"{label}: transparent table"
        print(f"ok  {label}: {len(expect)} colours, {swapped} of {len(m.bitmaps)} bitmaps swapped")

    m.dark = False
    dark_bitmaps = False
    check("Dark Mode off", colours)
    m.dark = dark_bitmaps = True
    check("Dark Mode on", {**colours, **dark})
    kept = m.bitmaps.pop(dt.DARK_BITMAP)   # a dark bitmap missing from the image DB: keep the light ones
    check("Dark Mode on, a dark bitmap missing", {**colours, **dark})
    m.bitmaps[dt.DARK_BITMAP] = kept
    assert dt.dark_bitmap(dt.STATUS_BAR_LIGHT) == dt.STATUS_BAR_DARK and dt.dark_bitmap(0x0DAD0159) == 0x0DAD0172
    assert m.key_seen == "General.Rotate", m.key_seen
    changed = sum(1 for cid in colours if (dark.get(cid) or colours[cid]) != colours[cid])
    print(f"    {changed} of {len(colours)} colours differ; setting read from {m.key_seen!r}")
    m.prefs_exist = False
    dark_bitmaps = False
    check("Dark Mode on, preferences not created yet", colours)

    # rotation readers: the byte read from the setting is replaced by a constant 1
    for a in dt.ROTATE_READS:
        assert m.body[a - dt.BASE:a - dt.BASE + 2] == bytes.fromhex("0120"), hex(a)
    print("ok  rotation readers always see On")
    return 0


if __name__ == "__main__":
    sys.exit(main())
