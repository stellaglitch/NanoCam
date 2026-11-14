"""PHOTO + CLIP: each photo also records a short clip, so it shows up in Camera Roll.

Camera Roll only lists items the iPod's own recorder registered (anything copied in
gets purged, even a genuine video; docs/firmware-notes.md sections 23-27). So in
Photo Camera:
  1st press: save the numbered PIC_NNNN.jpg (+ shutter sound), then start recording
             through the camera's own, unmodified center-button code
  2nd press: stop recording (same unmodified code)
The clip is a normal registered video whose thumbnail is the scene; the JPEG is the
full-quality photo. Video Camera is unchanged.

Mode flag (the photo_mode.py "flag" byte): 0 = Video Camera, 1 = Photo Camera,
2 = Photo Camera with a clip running.

Space: the 244-byte cave is full, so the new shutter logic (SHUTTER2) goes into the
debug .yuv dump FUN_08106838 (144 bytes). Its only call, at 0x080f55da (behind a
debug flag that is 0), becomes two NOPs, so that code can never run as itself.
The camera dispatcher hook at 0x080c8602 now calls SHUTTER2 instead of SHUTTER.

Usage:
    python patches/photo_clip.py firmware/n5g-retailos.dec firmware/n5g-photo-clip.dfu
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from nanocam import thumb as t  # noqa: E402
from nanocam.img1 import Img1  # noqa: E402
from nanocam.patch import Patch, apply  # noqa: E402
import photo_mode as pm  # noqa: E402

YUV_DUMP = 0x08106838           # debug raw-frame dump, 144 bytes (to 0x081068c8, where its strings start)
YUV_DUMP_END = 0x081068C8
YUV_DUMP_CALL = 0x080F55DA      # bl FUN_08106838, only reached when *(u8*)0x08550950 != 0
NOP = bytes.fromhex("c046")


def build_shutter2(flag: int, take_numbered: int) -> tuple[bytes, dict[str, int]]:
    s = t.Asm(YUV_DUMP)
    R = s.ref
    s("SHUTTER2")
    s(t.push([4], lr=True))
    R(2, lambda a, L: t.ldr_pc(a, 4, L["lit_flag"]))   # r4 = &flag
    s(t.ldrb(0, 4, 0))
    s(t.cmp_imm(0, 0))
    R(2, lambda a, L: t.bcond("eq", a, L["original"]))  # Video Camera: record as normal
    s(t.cmp_imm(0, 2))
    R(2, lambda a, L: t.bcond("eq", a, L["stop_clip"]))
    # mode 1: take the photo, then start the clip
    R(4, lambda a, L: t.bl(a, take_numbered))
    s(t.movs_imm(0, 2))
    s(t.strb(0, 4, 0))
    R(2, lambda a, L: t.b(a, L["original"]))
    s("stop_clip")                                      # mode 2: stop the clip
    s(t.movs_imm(0, 1))
    s(t.strb(0, 4, 0))
    s("original")
    s(t.adds_imm(5, 0xFF))                              # the two instructions the hook replaced
    s(t.adds_imm(5, 5))
    s(t.pop([4], pc=True))                              # back to 0x080c8606: state check, post(8)
    s("align4")
    s("lit_flag"); s(struct.pack("<I", flag))
    code, labels = s.build()
    if YUV_DUMP + len(code) > YUV_DUMP_END:
        raise ValueError(f"SHUTTER2 too big: {len(code)} bytes")
    return code, labels


def clip_patches(body: bytes) -> list[Patch]:
    cave, L = pm.build_cave()
    code, L2 = build_shutter2(L["flag"], L["TAKE_NUMBERED"])
    old = body[YUV_DUMP - pm.BASE:YUV_DUMP - pm.BASE + len(code)]
    return [
        Patch(YUV_DUMP_CALL - pm.BASE, t.bl(YUV_DUMP_CALL, YUV_DUMP), NOP + NOP),
        Patch(YUV_DUMP - pm.BASE, old, code),
    ]


def build_all(body: bytes) -> list[Patch]:
    patches = pm.build_all(body)
    _, L = pm.build_cave()
    code, L2 = build_shutter2(L["flag"], L["TAKE_NUMBERED"])
    # Retarget the dispatcher hook from SHUTTER to SHUTTER2.
    hook = next(p for p in patches if p.offset == pm.SHUTTER_HOOK - pm.BASE)
    patches[patches.index(hook)] = Patch(hook.offset, hook.old, t.bl(pm.SHUTTER_HOOK, L2["SHUTTER2"]))
    return patches + clip_patches(body)


def main() -> int:
    src, dst = sys.argv[1], sys.argv[2]
    img = Img1.parse(Path(src).read_bytes())
    patches = build_all(img.body)
    body = apply(img.body, patches)
    _, L = pm.build_cave()
    code, L2 = build_shutter2(L["flag"], L["TAKE_NUMBERED"])
    print(f"  SHUTTER2 {L2['SHUTTER2']:#010x}, {len(code)} of {YUV_DUMP_END - YUV_DUMP} bytes; flag {L['flag']:#010x}")
    for p in patches[-3:]:
        print(f"{p.offset:#09x}  {p.old.hex()[:24]} -> {p.new.hex()[:48]}")
    Path(dst).write_bytes(Img1.make_unsigned(body, entrypoint=img.header.entrypoint).to_bytes())
    print(f"wrote {dst} ({len(patches)} patches)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
