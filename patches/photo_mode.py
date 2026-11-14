"""PHOTO MODE v2: Photo Camera takes numbered photos, Video Camera records as normal.

Builds on take_photo.py (v1, proven: it wrote a valid 640x480 IMG_9000.jpg).

How it works
------------
1. Mode flag. The Photo Camera menu item keeps its original "chosen" handler,
   HandleComposersSelected (only its label and hilite are changed). In the main
   menu dispatcher FUN_080c3188 we redirect two calls:
     HandleComposersSelected branch: bl 0x080dd9ec -> bl PHOTO_SEL (flag = 1, open camera)
     HandleCameraSelected branch:    bl 0x080dd08c -> bl VIDEO_SEL (flag = 0, open camera)
   Both stubs then call the real "open camera" method 0x080dd08c.
2. Shutter. In the camera dispatcher FUN_080c85c4 the center-button branch
   starts with `adds r5,#0xff; adds r5,#5` (4 bytes) at 0x080c8602. Those become
   `bl SHUTTER`. SHUTTER either redoes those two adds and returns (video: the
   original code continues and records), or takes a photo and jumps to the
   dispatcher's "return 1" exit.
3. Numbering. TAKE_NUMBERED tries /DCIM/000APPLE/PIC_0000.jpg, PIC_0001.jpg, ...
   with the firmware's own file-exists check FUN_08196cb8 and photographs to
   the first name that's free, so no counter has to be stored.

Firmware helpers used (all checked in Ghidra, docs/firmware-notes.md section 16):
  0x0827f444  String init (empty)        0x0818ebc0  String destroy
  0x08196c00  sprintf into a String      0x08273378  vsnprintf(buf, n, fmt, va)
  0x08196cb8  file exists(String, vol)   0x0809c3e6  TakePhoto(pipeline, path, cb)

Usage:
    python patches/photo_mode.py firmware/n5g-retailos.dec firmware/n5g-photo-mode.dfu
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
from nanocam.resources import ResourceDB  # noqa: E402
from photo_camera_menu import build_patches as menu_patches  # noqa: E402

BASE = 0x07FD1D84

# firmware functions
TAKE_PHOTO = 0x0809C3E6
OPEN_CAMERA = 0x080DD08C       # main menu "CameraSelected" method
COMPOSERS_SELECTED = 0x080DD9EC
STR_INIT = 0x0827F444
STR_DESTROY = 0x0818EBC0
STR_SPRINTF = 0x08196C00
FILE_EXISTS = 0x08196CB8
STR_CSTR = 0x081909A4
SOUND_LOAD = 0x082682AC        # load(player, "Resources/Sounds/x.wav") -> ok
SOUND_PLAY = 0x08196642        # play(player, 1)
CLICK_PLAYER = 0x086CA1FC      # the click-wheel sound player (FUN_08032870)
CLICK_LOADED = 0x085509D0      # its "clicker.wav is loaded" byte
CAMERA_WAV = 0x08057C1C        # "Resources/Sounds/camera.wav" in the firmware
PIPELINE_GLOBAL = 0x086BA368

# patch sites
MENU_COMPOSERS_CALL = 0x080C393A   # bl 0x080dd9ec
MENU_CAMERA_CALL = 0x080C39BC      # bl 0x080dd08c
SHUTTER_HOOK = 0x080C8602          # adds r5,#0xff ; adds r5,#5
RETURN_TRUE = 0x080C866E           # movs r0,#1 ; pop {r1-r7,pc}

CAVE = 0x08276B0C              # first 4-aligned byte after the function ending at 0x08276b0a
CAVE_END = 0x08276C00

FMT = b"/DCIM/000APPLE/PIC_%04d.jpg\0"   # not IMG_: the DCIM scan purges IMG_NNNN.* (notes 23c)
EXT_AT = len("/DCIM/000APPLE/PIC_0000")   # cut ".jpg" here for TakePhoto


def bl(target):
    return lambda a, L: t.bl(a, L[target] if isinstance(target, str) else target)


def build_cave() -> tuple[bytes, dict[str, int]]:
    s = t.Asm(CAVE)
    R = s.ref

    # --- PHOTO_SEL / VIDEO_SEL(r0=this, r1=arg): set the flag, then open the camera
    s("PHOTO_SEL")
    s(t.movs_imm(2, 1))
    R(2, lambda a, L: t.b(a, L["set_mode"]))
    s("VIDEO_SEL")
    s(t.movs_imm(2, 0))
    s("set_mode")
    s(t.push([4], lr=True))
    R(2, lambda a, L: t.ldr_pc(a, 3, L["lit_flag"]))
    s(t.strb(2, 3, 0))
    R(4, bl(OPEN_CAMERA))
    s(t.pop([4], pc=True))

    # --- SHUTTER: called from the camera dispatcher in place of two adds
    s("SHUTTER")
    s(t.push([4], lr=True))
    R(2, lambda a, L: t.ldr_pc(a, 0, L["lit_flag"]))
    s(t.ldrb(0, 0, 0))
    s(t.cmp_imm(0, 0))
    R(2, lambda a, L: t.bcond("ne", a, L["photo"]))
    s(t.adds_imm(5, 0xFF))          # the original instructions
    s(t.adds_imm(5, 5))
    s(t.pop([4], pc=True))          # back to 0x080c8606: record as normal
    s("photo")
    R(4, bl("TAKE_NUMBERED"))
    s(t.pop([4]))
    s(t.pop([0]))                   # drop the return address
    R(2, lambda a, L: t.ldr_pc(a, 0, L["lit_return"]))
    s(t.bx(0))                      # -> "movs r0,#1; pop": button handled

    # --- TAKE_NUMBERED: photograph to the first free PIC_NNNN.jpg, then play camera.wav
    # stack: [sp+0] String (8 bytes), [sp+8] empty callback (12 zero bytes)
    # r4 = n, r5 = pipeline
    s("TAKE_NUMBERED")
    s(t.push([4, 5, 6, 7], lr=True))
    s(t.sub_sp(20))
    R(2, lambda a, L: t.ldr_pc(a, 5, L["lit_global"]))
    s(t.ldr_reg0(5, 5))
    s(t.cmp_imm(5, 0))
    R(2, lambda a, L: t.bcond("eq", a, L["out"]))
    s(t.movs_imm(4, 0))
    s("loop")
    s(t.add_sp_rd(0, 0))
    R(4, bl(STR_INIT))
    s(t.add_sp_rd(0, 0))
    R(2, lambda a, L: t.adr(a, 1, L["fmt"]))
    s(t.mov_lo(2, 4))
    R(4, bl(STR_SPRINTF))
    s(t.add_sp_rd(0, 0))
    s(t.movs_imm(1, 0))
    R(4, bl(FILE_EXISTS))
    s(t.cmp_imm(0, 0))
    R(2, lambda a, L: t.bcond("eq", a, L["found"]))
    s(t.add_sp_rd(0, 0))
    R(4, bl(STR_DESTROY))
    s(t.adds_imm(4, 1))
    s(t.lsrs_imm(0, 4, 13))         # keep going while n < 8192
    R(2, lambda a, L: t.bcond("eq", a, L["loop"]))
    R(2, lambda a, L: t.b(a, L["out"]))
    s("found")
    s(t.add_sp_rd(0, 0))
    R(4, bl(STR_CSTR))
    s(t.mov_lo(1, 0))
    s(t.movs_imm(2, 0))
    s(t.strb(2, 1, EXT_AT))         # drop ".jpg"; the encoder adds it back
    s(t.str_sp(2, 8))               # callback = {0, 0, 0}
    s(t.str_sp(2, 12))
    s(t.str_sp(2, 16))
    s(t.mov_lo(0, 5))
    s(t.add_sp_rd(2, 8))
    R(4, bl(TAKE_PHOTO))            # copies the path, so the String can go
    s(t.add_sp_rd(0, 0))
    R(4, bl(STR_DESTROY))
    # Shutter sound: borrow the click-wheel sound player (as FUN_08032870 does),
    # load camera.wav into it and play, then mark it unloaded so the next
    # click reloads clicker.wav.
    R(2, lambda a, L: t.ldr_pc(a, 4, L["lit_player"]))
    s(t.mov_lo(0, 4))
    R(2, lambda a, L: t.ldr_pc(a, 1, L["lit_wav"]))
    R(4, bl(SOUND_LOAD))
    s(t.cmp_imm(0, 0))
    R(2, lambda a, L: t.bcond("eq", a, L["unload"]))
    s(t.mov_lo(0, 4))
    s(t.adds_imm(0, 0x40))
    s(t.movs_imm(1, 4))
    s(t.strb(1, 0, 2))              # player+0x42 = 4
    s(t.movs_imm(1, 0))
    s(t.strb(1, 0, 0))              # player+0x40 = 0
    R(2, lambda a, L: t.ldr_pc(a, 0, L["lit_volume"]))
    s(t.str_imm(0, 4, 0x20))        # player+0x20 = 0x7fff
    s(t.mov_lo(0, 4))
    s(t.movs_imm(1, 1))
    R(4, bl(SOUND_PLAY))
    s("unload")
    R(2, lambda a, L: t.ldr_pc(a, 0, L["lit_loaded"]))
    s(t.movs_imm(1, 0))
    s(t.strb(1, 0, 0))
    s("out")
    s(t.add_sp(20))
    s(t.pop([4, 5, 6, 7], pc=True))

    # --- data
    s("align4")
    s("lit_flag");   s(bytes(4))   # patched below to point at "flag"
    s("lit_global"); s(struct.pack("<I", PIPELINE_GLOBAL))
    s("lit_return"); s(struct.pack("<I", RETURN_TRUE | 1))
    s("lit_player"); s(struct.pack("<I", CLICK_PLAYER))
    s("lit_wav");    s(struct.pack("<I", CAMERA_WAV))
    s("lit_volume"); s(struct.pack("<I", 0x7FFF))
    s("lit_loaded"); s(struct.pack("<I", CLICK_LOADED))
    s("flag");       s(bytes(4))      # 1 = photo mode (written at run time)
    s("fmt");        s(FMT)

    code, labels = s.build()
    off = labels["lit_flag"] - CAVE
    code = code[:off] + struct.pack("<I", labels["flag"]) + code[off + 4:]
    if CAVE + len(code) > CAVE_END:
        raise ValueError(f"cave overflow: {len(code)} bytes (have {CAVE_END - CAVE})")
    return code, labels


def photo_patches(body: bytes) -> list[Patch]:
    code, L = build_cave()
    if body[CAVE - BASE:CAVE - BASE + len(code)] != bytes(len(code)):
        raise ValueError("code cave isn't empty; wrong firmware?")
    return [
        Patch(CAVE - BASE, bytes(len(code)), code),
        Patch(MENU_COMPOSERS_CALL - BASE, t.bl(MENU_COMPOSERS_CALL, COMPOSERS_SELECTED),
              t.bl(MENU_COMPOSERS_CALL, L["PHOTO_SEL"])),
        Patch(MENU_CAMERA_CALL - BASE, t.bl(MENU_CAMERA_CALL, OPEN_CAMERA),
              t.bl(MENU_CAMERA_CALL, L["VIDEO_SEL"])),
        Patch(SHUTTER_HOOK - BASE, t.adds_imm(5, 0xFF) + t.adds_imm(5, 5),
              t.bl(SHUTTER_HOOK, L["SHUTTER"])),
    ]


def build_all(body: bytes) -> list[Patch]:
    # Keep the menu label + hilite patches, but NOT the one that sends the
    # Photo Camera item's "chosen" event to HandleCameraSelected: it must stay
    # HandleComposersSelected so the dispatcher can tell the two items apart.
    db = ResourceDB(body)
    composers_sel = struct.pack("<H", db.symbol_id("HandleComposersSelected"))
    menu = [p for p in menu_patches(body) if p.old != composers_sel]
    if len(menu) != 5:
        raise ValueError("unexpected menu patch set")
    return menu + photo_patches(body)


def main() -> int:
    src, dst = sys.argv[1], sys.argv[2]
    img = Img1.parse(Path(src).read_bytes())
    patches = build_all(img.body)
    body = apply(img.body, patches)
    code, L = build_cave()
    for name in ("PHOTO_SEL", "VIDEO_SEL", "SHUTTER", "TAKE_NUMBERED", "flag", "fmt"):
        print(f"  {name:14} {L[name]:#010x}")
    print(f"  cave used: {len(code)} of {CAVE_END - CAVE} bytes")
    for p in patches:
        print(f"{p.offset:#09x}  {p.old.hex()} -> {p.new.hex()}")
    Path(dst).write_bytes(Img1.make_unsigned(body, entrypoint=img.header.entrypoint).to_bytes())
    print(f"wrote {dst} ({len(patches)} patches)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
