"""PHOTOS SLOT WRITER: each photo also appears in the stock Photos app.

The Photos library on the iPod (D:\\Photos) is made by an iTunes sync of numbered
placeholder pictures. Each placeholder owns fixed slots in the .ithmb files
(docs/firmware-notes.md section 28):
    F1087_1.ithmb  384x384 RGB565, full-screen view, slot n at n * 0x48000
    F1066_1.ithmb   64x64  RGB565, grid thumbnail,   slot n at n * 0x2000
The JPEG encoder FUN_080f533c already calls the (disabled) debug dump at 0x080f55da
with r0 = the photo's path ("/DCIM/000APPLE/PIC_NNNN.jpg") and r1 = the raw frame
(640x480 YUYV, landscape; EXIF orientation 6). This patch points that call at
WRITE_SLOTS, which converts the frame and overwrites slot (NNNN mod SLOTS):
    F1087: the frame rotated 90 deg clockwise, scaled to 288x384, centred (48 px black
           bars left and right)
    F1066: the centre 480x480 square of the upright frame, scaled to 64x64
Nothing in the Photo Database changes.

Space comes from Voice Memos (section 26): its only entry, FUN_082003dc (called from
the two menu dispatchers), returns immediately, and the code goes into two of its
screen-controller methods:
    WRITE_SLOTS   TCVoiceMemosMainMenu[85]        0x080bc69c .. 0x080bc7ca (302 bytes)
    PIX + strings TCVoiceMemosLabelSelectMenu[68] 0x080a9224 .. 0x080a92dc (184 bytes)
    file helpers  TCVoiceMemosContextMenu[68]     0x080a8548 .. 0x080a8600 (184 bytes)
    FIX_EXIF      TCVoiceMemosTimedStatus[68]     0x080a887c .. 0x080a8934 (184 bytes)

Upside down (UI rotation *(FUN_081ab630()+0x290) == 180): the frame is mirrored through
its centre before sampling (= rotated 90 deg anticlockwise instead of clockwise), and the
JPEG's EXIF orientation (big-endian u16 at byte 54) is changed from 6 to 8.

Firmware calls used (section 28 notes):
    FUN_0818eb44(size)                          operator new
    FUN_0827f35c(obj, cpath, ro=0, 0, 0x400, 1, 0) -> file (opened for writing)
    FUN_0827ddec(file, _, off_lo, off_hi, [whence=0]) -> 0 on success (seek)
    FUN_0823b61a(file, len, buf, &written)      write
    file->vtable[1](file)                       close + delete

Usage:
    python patches/photos_slot.py firmware/n5g-retailos.dec firmware/n5g-photos-slot.dfu [slots] [next PIC number]

slot = (PIC number + offset) mod slots, where offset makes [next PIC number] land in slot 0
(the first placeholder, top of the grid) and later photos fill the following slots.
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

BASE = pm.BASE

# firmware
OP_NEW = 0x0818EB44
FILE_OPEN = 0x0827F35C
FILE_SEEK = 0x0827DDEC
FILE_WRITE = 0x0823B61A
DUMP_CALL = 0x080F55DA          # bl FUN_08106838 (debug dump), behind a flag check
DUMP_SKIP = 0x080F55D0          # beq 0x080f55de: skip the dump when the flag is 0
DUMP_DONE = 0x080F55DE
DEBUG_DUMP = 0x08106838
VOICE_MEMOS_ENTRY = 0x082003DC  # push {r4,lr} -> bx lr
UI_SYSTEM = 0x081AB630          # returns the UI object; +0x290 = screen rotation in degrees
ROTATION_AT = 0x290             # 0 / 90 / 180 / 270 (camera's own copy: FUN_080e5d66 -> cam+0x13c)
UPSIDE_DOWN = 180
# angle -> JPEG EXIF orientation (the camera always writes 6 = portrait, rotate 90 CW):
#   0 -> 6 (untouched), 180 -> 8, 90 -> 1, 270 -> 3
LAND_TOP, LAND_H = 84, 216      # landscape picture: 288x216 centred in the 288x384 content area
EXIF_ORIENTATION_LO = 55        # the camera's JPEGs: big-endian u16 orientation at byte 54 (= 6)

# donor space
# Donor space moved from Voice Memos (now restored) to the Nike+ heart-rate-monitor screen
# controllers (docs/firmware-notes.md section 36). Those screens must not be opened.
REGION_A = (0x08181904, 0x08181A52)   # ...HeartMonitorLinkingInstructions addon[89] (334 bytes)
REGION_B = (0x08181834, 0x081818EC)   # ...HeartMonitorLinkingInstructions addon[68] (184 bytes): PIX
REGION_C = (0x08181500, 0x081815B8)   # ...Settings_HeartMonitor addon[68] (184 bytes): file helpers, PIXF
REGION_D = (0x081811CC, 0x08181284)   # ...HeartMonitorUnlinking addon[68] (184 bytes): FINISH, FIX_EXIF
REGION_E = (0x08180B5C, 0x08180C14)   # ...HeartMonitorLinking addon[68] (184 bytes): SAMPLE87, SAMPLE66

NOP = bytes.fromhex("c046")
BX_LR = bytes.fromhex("7047")
NUM_AT = len("/DCIM/000APPLE/PIC_")   # index of the 4 photo-number digits in the path

# stack frame of WRITE_SLOTS
ARGS = 0          # [sp+0..11]  extra call arguments
WRITTEN = 12      # [sp+12]     bytes written
RX = 16           # [sp+16]     current raw column
SLOT = 20         # [sp+20]     slot number
ROW = 24          # [sp+24]     row buffer, 384 * 2 bytes
FLIP = ROW + 768  # [sp+792]    1 if the iPod was upside down when the photo was taken
PATH = FLIP + 4   # [sp+796]    the photo's path (for the EXIF fix)
LAND = PATH + 4   # [sp+800]    1 if the iPod was sideways (90 or 270 degrees)
FRAME_SIZE = LAND + 4        # 804: keeps sp 8-byte aligned (push of 5 regs = 20 bytes)


def build_pix(base: int) -> tuple[bytes, dict[str, int]]:
    """PIX(r0 = frame, r1 = raw x, r2 = raw y) -> r0 = RGB565. Clobbers r1-r3."""
    s = t.Asm(base)
    R = s.ref
    s("PIX")
    s(t.push([4, 5, 6], lr=True))
    # r3 = (y*640 + x) * 2   (640 = 5 << 7)
    s(t.lsls_imm(3, 2, 2)); s(t.adds_reg(3, 3, 2)); s(t.lsls_imm(3, 3, 7)); s(t.adds_reg(3, 3, 1))
    s(t.lsls_imm(3, 3, 1))
    s(t.adds_reg(4, 0, 3)); s(t.ldrb(5, 4, 0))            # r5 = Y
    s(t.lsrs_imm(3, 3, 2)); s(t.lsls_imm(3, 3, 2))       # start of the Y0 U Y1 V group
    s(t.adds_reg(4, 0, 3)); s(t.ldrb(1, 4, 1)); s(t.ldrb(2, 4, 3))
    s(t.subs_imm(1, 128)); s(t.subs_imm(2, 128))          # r1 = U-128, r2 = V-128

    def clamp(r):
        R(2, lambda a, L, r=r: t.bcond("ge", a, a + 4))   # skip next if >= 0
        s(t.movs_imm(r, 0))
        s(t.cmp_imm(r, 255))
        R(2, lambda a, L, r=r: t.bcond("le", a, a + 4))
        s(t.movs_imm(r, 255))

    # R = Y + (359 v >> 8)
    R(2, lambda a, L: t.ldr_pc(a, 3, L["k359"])); s(t.muls(3, 2)); s(t.asrs_imm(3, 3, 8))
    s(t.adds_reg(3, 3, 5)); s(t.cmp_imm(3, 0)); clamp(3)
    # G = Y - ((88 u + 183 v) >> 8)
    s(t.movs_imm(4, 88)); s(t.muls(4, 1)); s(t.movs_imm(6, 183)); s(t.muls(6, 2))
    s(t.adds_reg(4, 4, 6)); s(t.asrs_imm(4, 4, 8)); s(t.subs_reg(4, 5, 4)); s(t.cmp_imm(4, 0)); clamp(4)
    # B = Y + (454 u >> 8)
    R(2, lambda a, L: t.ldr_pc(a, 6, L["k454"])); s(t.muls(6, 1)); s(t.asrs_imm(6, 6, 8))
    s(t.adds_reg(6, 6, 5)); s(t.cmp_imm(6, 0)); clamp(6)
    # RGB565
    s(t.lsrs_imm(3, 3, 3)); s(t.lsls_imm(3, 3, 11))
    s(t.lsrs_imm(4, 4, 2)); s(t.lsls_imm(4, 4, 5)); s(t.orrs(3, 4))
    s(t.lsrs_imm(6, 6, 3)); s(t.orrs(3, 6))
    s(t.mov_lo(0, 3))
    s(t.pop([4, 5, 6], pc=True))
    s("align4")
    s("k359"); s(struct.pack("<I", 359))
    s("k454"); s(struct.pack("<I", 454))
    s("path87"); s(b"/Photos/Thumbs/F1087_1.ithmb\0")
    s("path66"); s(b"/Photos/Thumbs/F1066_1.ithmb\0")
    return s.build()


def build_helpers(base: int, pix: dict[str, int] | None = None) -> tuple[bytes, dict[str, int]]:
    """OPEN_SEEK, WRITE_ROW, CLOSE, PIXF, FIX_EXIF: called only from WRITE_SLOTS (they reach into its frame)."""
    s = t.Asm(base)
    R = s.ref
    pix = pix or {"PIX": base}
    bl = lambda target: R(4, lambda a, L, tg=target: t.bl(a, (L.get(tg) or pix[tg]) if isinstance(tg, str) else tg))

    # PIXF(r0 = frame, r1 = x, r2 = y, r3 = flip): PIX, mirrored through the centre if r3
    s("PIXF")
    s(t.push([4], lr=True))
    s(t.cmp_imm(3, 0)); R(2, lambda a, L: t.bcond("eq", a, L["pixf_go"]))
    R(2, lambda a, L: t.ldr_pc(a, 3, L["k639"])); s(t.subs_reg(1, 3, 1))
    R(2, lambda a, L: t.ldr_pc(a, 3, L["k479h"])); s(t.subs_reg(2, 3, 2))
    s("pixf_go")
    bl("PIX")
    s(t.pop([4], pc=True))

    # OPEN_SEEK(r0 = path, r1 = stride) -> r0 = file or 0. Uses the caller's frame
    # (lr was pushed by WRITE_SLOTS; this is a leaf-ish helper with its own push).
    s("OPEN_SEEK")
    s(t.push([4, 5, 6], lr=True))
    s(t.mov_lo(4, 0)); s(t.mov_lo(5, 1))
    s(t.movs_imm(0, 0x54)); bl(OP_NEW)
    s(t.mov_lo(1, 4)); s(t.mov_lo(4, 0))                  # r4 = obj
    s(t.sub_sp(16))
    s(t.movs_imm(2, 1)); s(t.lsls_imm(2, 2, 10)); s(t.str_sp(2, 0))   # [sp] = 0x400
    s(t.movs_imm(2, 1)); s(t.str_sp(2, 4))                           # [sp+4] = 1
    s(t.movs_imm(2, 0)); s(t.str_sp(2, 8))                           # [sp+8] = 0
    s(t.mov_lo(0, 4)); s(t.movs_imm(3, 0))                           # r2 = 0 (writable)
    bl(FILE_OPEN)
    s(t.mov_lo(6, 0)); s(t.cmp_imm(6, 0)); R(2, lambda a, L: t.bcond("eq", a, L["os_out"]))
    # seek to slot * stride
    s(t.ldr_sp(2, 16 + 16 + SLOT))      # caller's [sp+SLOT]: our 16-byte args + our push {r4-r6,lr}
    s(t.muls(2, 5))
    s(t.movs_imm(3, 0)); s(t.str_sp(3, 0))
    s(t.mov_lo(0, 6))
    bl(FILE_SEEK)
    s(t.cmp_imm(0, 0)); R(2, lambda a, L: t.bcond("eq", a, L["os_out"]))
    s(t.mov_lo(0, 6)); bl("CLOSE"); s(t.movs_imm(6, 0))
    s("os_out")
    s(t.mov_lo(0, 6))
    s(t.add_sp(16))
    s(t.pop([4, 5, 6], pc=True))

    # WRITE_ROW(r0 = file, r1 = length): writes the caller's row buffer
    s("WRITE_ROW")
    s(t.push([4], lr=True))
    s(t.add_sp_rd(2, 8 + ROW)); s(t.add_sp_rd(3, 8 + WRITTEN))
    bl(FILE_WRITE)
    s(t.pop([4], pc=True))

    # CLOSE(r0 = file): file->vtable[1](file)
    s("CLOSE")
    s(t.push([4], lr=True))
    s(t.ldr_imm(1, 0, 0)); s(t.ldr_imm(1, 1, 4)); s(t.blx_reg(1))
    s(t.pop([4], pc=True))
    s("align4")
    s("k639"); s(struct.pack("<I", 639))
    s("k479h"); s(struct.pack("<I", 479))

    return s.build()


def build_exif(base: int, helpers: dict[str, int]) -> tuple[bytes, dict[str, int]]:
    """FIX_EXIF: lives in its own donor region; uses CLOSE from the helpers."""
    s = t.Asm(base)
    R = s.ref
    bl = lambda target: R(4, lambda a, L, tg=target: t.bl(a, (L.get(tg) or helpers[tg]) if isinstance(tg, str) else tg))

    # FINISH(): if [caller sp+FLIP]: FIX_EXIF([caller sp+PATH])
    s("FINISH")
    s(t.push([4], lr=True))
    s(t.add_sp_rd(1, 8)); R(2, lambda a, L: t.ldr_pc(a, 2, L["k_flip_at"])); s(t.adds_reg(1, 1, 2))
    s(t.ldr_imm(2, 1, 0)); s(t.ldr_imm(3, 1, LAND - FLIP)); s(t.ldr_imm(0, 1, PATH - FLIP))
    s(t.cmp_imm(3, 0)); R(2, lambda a, L: t.bcond("ne", a, L["fin_land"]))
    s(t.cmp_imm(2, 0)); R(2, lambda a, L: t.bcond("eq", a, L["fin_out"]))
    s(t.movs_imm(1, 8)); R(2, lambda a, L: t.b(a, L["fin_fix"]))     # upside-down portrait
    s("fin_land")
    s(t.movs_imm(1, 1)); s(t.cmp_imm(2, 0)); R(2, lambda a, L: t.bcond("eq", a, L["fin_fix"]))
    s(t.movs_imm(1, 3))                                              # landscape rotated 180
    s("fin_fix")
    bl("FIX_EXIF")
    s("fin_out")
    s(t.pop([4], pc=True))

    # FIX_EXIF(r0 = path): set the JPEG's EXIF orientation to 8 (upside-down portrait)
    s("FIX_EXIF")                                          # (r0 = path, r1 = orientation)
    s(t.push([4, 5, 6], lr=True))
    s(t.mov_lo(4, 0)); s(t.mov_lo(5, 1))
    s(t.movs_imm(0, 0x54)); bl(OP_NEW)
    s(t.mov_lo(1, 4)); s(t.mov_lo(4, 0))
    s(t.sub_sp(24))
    s(t.movs_imm(2, 1)); s(t.lsls_imm(2, 2, 10)); s(t.str_sp(2, 0))
    s(t.movs_imm(2, 1)); s(t.str_sp(2, 4))
    s(t.movs_imm(2, 0)); s(t.str_sp(2, 8))
    s(t.mov_lo(0, 4)); s(t.movs_imm(3, 0))
    bl(FILE_OPEN)
    s(t.mov_lo(6, 0)); s(t.cmp_imm(6, 0)); R(2, lambda a, L: t.bcond("eq", a, L["fx_out"]))
    s(t.movs_imm(2, EXIF_ORIENTATION_LO)); s(t.movs_imm(3, 0)); s(t.str_sp(3, 0)); s(t.mov_lo(0, 6))
    bl(FILE_SEEK)
    s(t.cmp_imm(0, 0)); R(2, lambda a, L: t.bcond("ne", a, L["fx_close"]))
    s(t.str_sp(5, 16))
    s(t.mov_lo(0, 6)); s(t.movs_imm(1, 1)); s(t.add_sp_rd(2, 16)); s(t.add_sp_rd(3, 20))
    bl(FILE_WRITE)
    s("fx_close")
    s(t.mov_lo(0, 6)); bl("CLOSE")
    s("fx_out")
    s(t.add_sp(24))
    s(t.pop([4, 5, 6], pc=True))
    s("align4")
    s("k_flip_at"); s(struct.pack("<I", FLIP))
    return s.build()


def build_sample(base: int, helpers: dict[str, int]) -> tuple[bytes, dict[str, int]]:
    """SETUP, SAMPLE87 / SAMPLE66(r0 = ox, r1 = oy) -> r0 = RGB565, using r5 = frame and the
    caller's (WRITE_SLOTS) FLIP / LAND.
    Portrait: the frame rotated 90 CW (mirrored through its centre if FLIP).
    Landscape: the frame as-is (mirrored if FLIP); in F1087 it fills rows 84..299."""
    s = t.Asm(base)
    R = s.ref
    bl = lambda target: R(4, lambda a, L, tg=target: t.bl(a, (L.get(tg) or helpers[tg]) if isinstance(tg, str) else tg))
    F = 8   # push {r4, lr}

    # SETUP(r0 = path): [caller sp+PATH] = path; [caller sp+FLIP] = (UI rotation == 180)
    s("SETUP")
    s(t.push([4, 5], lr=True)); s(t.sub_sp(4))            # 16 bytes: caller's frame at sp+16
    s(t.add_sp_rd(4, 16)); R(2, lambda a, L: t.ldr_pc(a, 1, L["k_flip_at"])); s(t.adds_reg(4, 4, 1))
    s(t.str_imm(0, 4, PATH - FLIP))                       # r4 = &caller[FLIP]; path at +4
    bl(UI_SYSTEM)
    R(2, lambda a, L: t.ldr_pc(a, 1, L["k_rot"])); s(t.ldr_reg(0, 0, 1))
    s(t.movs_imm(1, 0)); s(t.movs_imm(2, 0))                 # r1 = flip, r2 = land
    s(t.cmp_imm(0, 180)); R(2, lambda a, L: t.bcond("ne", a, a + 4)); s(t.movs_imm(1, 1))
    s(t.cmp_imm(0, 90)); R(2, lambda a, L: t.bcond("ne", a, a + 4)); s(t.movs_imm(2, 1))
    R(2, lambda a, L: t.ldr_pc(a, 3, L["k270"])); s(t.cmp_reg(0, 3))
    R(2, lambda a, L: t.bcond("ne", a, a + 6)); s(t.movs_imm(1, 1)); s(t.movs_imm(2, 1))
    s(t.str_imm(1, 4, 0)); s(t.str_imm(2, 4, LAND - FLIP))
    s(t.add_sp(4)); s(t.pop([4, 5], pc=True))

    s("SAMPLE87")
    s(t.push([4], lr=True))
    s(t.ldr_sp(3, F + LAND)); s(t.cmp_imm(3, 0)); R(2, lambda a, L: t.bcond("ne", a, L["l87"]))
    R(2, lambda a, L: t.ldr_pc(a, 3, L["k1707"]))
    s(t.muls(0, 3)); s(t.lsrs_imm(0, 0, 10))                   # ox * 5/3
    s(t.muls(1, 3)); s(t.lsrs_imm(1, 1, 10))                   # rx = oy * 5/3
    R(2, lambda a, L: t.ldr_pc(a, 2, L["k479"])); s(t.subs_reg(2, 2, 0))   # ry = 479 - ox*5/3
    R(2, lambda a, L: t.b(a, L["go"]))
    s("l87")
    s(t.subs_imm(1, LAND_TOP)); R(2, lambda a, L: t.bcond("lt", a, L["black"]))
    s(t.cmp_imm(1, LAND_H)); R(2, lambda a, L: t.bcond("ge", a, L["black"]))
    R(2, lambda a, L: t.b(a, L["land"]))

    s("SAMPLE66")
    s(t.push([4], lr=True))
    s(t.ldr_sp(3, F + LAND)); s(t.cmp_imm(3, 0)); R(2, lambda a, L: t.bcond("ne", a, L["l66"]))
    s(t.movs_imm(3, 15))
    s(t.muls(0, 3)); s(t.lsrs_imm(0, 0, 1))                    # ox * 7.5
    s(t.muls(1, 3)); s(t.lsrs_imm(1, 1, 1)); s(t.adds_imm(1, 80))   # rx = 80 + oy * 7.5
    R(2, lambda a, L: t.ldr_pc(a, 2, L["k479"])); s(t.subs_reg(2, 2, 0))   # ry = 479 - ox*7.5
    R(2, lambda a, L: t.b(a, L["go"]))
    s("l66")
    s(t.movs_imm(3, 15))
    s(t.muls(1, 3)); s(t.lsrs_imm(2, 1, 1))                    # ry = oy * 7.5
    s(t.muls(0, 3)); s(t.lsrs_imm(1, 0, 1)); s(t.adds_imm(1, 80))   # rx = 80 + ox * 7.5
    R(2, lambda a, L: t.b(a, L["go"]))

    s("land")                                                   # F1087 landscape: scale 20/9
    R(2, lambda a, L: t.ldr_pc(a, 3, L["k2276"]))
    s(t.muls(1, 3)); s(t.lsrs_imm(2, 1, 10))                   # ry = (oy - 84) * 20/9
    s(t.muls(0, 3)); s(t.lsrs_imm(1, 0, 10))                   # rx = ox * 20/9
    s("go")
    s(t.mov_lo(0, 5)); s(t.ldr_sp(3, F + FLIP))
    bl("PIXF")
    s(t.pop([4], pc=True))
    s("black")
    s(t.movs_imm(0, 0))
    s(t.pop([4], pc=True))
    s("align4")
    s("k1707"); s(struct.pack("<I", 1707))
    s("k2276"); s(struct.pack("<I", 2276))
    s("k479"); s(struct.pack("<I", 479))
    s("k_flip_at"); s(struct.pack("<I", FLIP))
    s("k_rot"); s(struct.pack("<I", ROTATION_AT))
    s("k270"); s(struct.pack("<I", 270))
    return s.build()


def build_writer(base: int, pix: dict[str, int], helpers: dict[str, int], slots: int,
                 offset: int = 0) -> tuple[bytes, dict[str, int]]:
    """WRITE_SLOTS(r0 = path, r1 = frame)."""
    s = t.Asm(base)
    R = s.ref
    ext = {**helpers}
    bl = lambda target: R(4, lambda a, L, tg=target: t.bl(a, (L.get(tg) or ext[tg]) if isinstance(tg, str) else tg))

    s("WRITE_SLOTS")
    s(t.push([4, 5, 6, 7], lr=True))
    s(t.sub_sp(508)); s(t.sub_sp(FRAME_SIZE - 508))
    s(t.mov_lo(5, 1))                                     # r5 = frame
    s(t.mov_lo(6, 0)); bl("SETUP"); s(t.mov_lo(0, 6))   # [sp+PATH] = path, [sp+FLIP] = upside down
    # slot = the 4 digits at path[NUM_AT..] mod slots
    s(t.movs_imm(4, 0)); s(t.movs_imm(7, 0))
    s("digit")
    s(t.adds_reg(2, 0, 7)); s(t.ldrb(2, 2, NUM_AT)); s(t.subs_imm(2, 48))
    s(t.movs_imm(3, 10)); s(t.muls(4, 3)); s(t.adds_reg(4, 4, 2))
    s(t.adds_imm(7, 1)); s(t.cmp_imm(7, 4)); R(2, lambda a, L: t.bcond("lt", a, L["digit"]))
    if slots <= 255:                                      # 8-bit immediates
        if offset:
            s(t.adds_imm(4, offset))                      # so the next photo lands in slot 0
        s("mod")
        s(t.cmp_imm(4, slots)); R(2, lambda a, L: t.bcond("lt", a, L["mod_done"]))
        s(t.subs_imm(4, slots)); R(2, lambda a, L: t.b(a, L["mod"]))
    else:                                                 # 500, 1000 ...: from literals (r3 is free here)
        if offset:
            R(2, lambda a, L: t.ldr_pc(a, 3, L["k_offset"])); s(t.adds_reg(4, 4, 3))
        R(2, lambda a, L: t.ldr_pc(a, 3, L["k_slots"]))
        s("mod")
        s(t.cmp_reg(4, 3)); R(2, lambda a, L: t.bcond("lt", a, L["mod_done"]))
        s(t.subs_reg(4, 4, 3)); R(2, lambda a, L: t.b(a, L["mod"]))
    s("mod_done")
    s(t.str_sp(4, SLOT))
    # zero the row buffer (the black bars stay zero)
    s(t.movs_imm(0, 0)); s(t.add_sp_rd(1, ROW)); s(t.movs_imm(2, 192))   # 192 words
    s("zero")
    s(t.str_imm(0, 1, 0)); s(t.adds_imm(1, 4)); s(t.subs_imm(2, 1))
    R(2, lambda a, L: t.bcond("ne", a, L["zero"]))

    # ---- F1087: 384 rows of 384 px --------------------------------------------------
    R(2, lambda a, L: t.ldr_pc(a, 0, L["lit_path87"]))
    R(2, lambda a, L: t.ldr_pc(a, 1, L["lit_stride87"]))
    bl("OPEN_SEEK")
    s(t.mov_lo(6, 0)); s(t.cmp_imm(6, 0)); R(2, lambda a, L: t.bcond("eq", a, L["do66"]))
    s(t.movs_imm(7, 0))                                   # r7 = oy
    s("row87")
    s(t.movs_imm(4, 0))                                   # r4 = ox
    s("px87")
    s(t.mov_lo(0, 4)); s(t.mov_lo(1, 7))
    bl("SAMPLE87")
    s(t.add_sp_rd(1, ROW + 96)); s(t.lsls_imm(2, 4, 1)); s(t.adds_reg(1, 1, 2)); s(t.strh_imm(0, 1, 0))
    s(t.adds_imm(4, 1)); R(2, lambda a, L: t.ldr_pc(a, 3, L["k288"])); s(t.cmp_reg(4, 3))
    R(2, lambda a, L: t.bcond("lt", a, L["px87"]))
    s(t.mov_lo(0, 6)); R(2, lambda a, L: t.ldr_pc(a, 1, L["k768"]))
    bl("WRITE_ROW")
    s(t.adds_imm(7, 1)); R(2, lambda a, L: t.ldr_pc(a, 3, L["k384"])); s(t.cmp_reg(7, 3))
    R(2, lambda a, L: t.bcond("lt", a, L["row87"]))
    s(t.mov_lo(0, 6)); bl("CLOSE")

    # ---- F1066: 64 rows of 64 px from the centre square ----------------------------
    s("do66")
    R(2, lambda a, L: t.ldr_pc(a, 0, L["lit_path66"]))
    R(2, lambda a, L: t.ldr_pc(a, 1, L["lit_stride66"]))
    bl("OPEN_SEEK")
    s(t.mov_lo(6, 0)); s(t.cmp_imm(6, 0)); R(2, lambda a, L: t.bcond("eq", a, L["done"]))
    s(t.movs_imm(7, 0))
    s("row66")
    s(t.movs_imm(4, 0))
    s("px66")
    s(t.mov_lo(0, 4)); s(t.mov_lo(1, 7))
    bl("SAMPLE66")
    s(t.add_sp_rd(1, ROW)); s(t.lsls_imm(2, 4, 1)); s(t.adds_reg(1, 1, 2)); s(t.strh_imm(0, 1, 0))
    s(t.adds_imm(4, 1)); s(t.cmp_imm(4, 64)); R(2, lambda a, L: t.bcond("lt", a, L["px66"]))
    s(t.mov_lo(0, 6)); s(t.movs_imm(1, 128))
    bl("WRITE_ROW")
    s(t.adds_imm(7, 1)); s(t.cmp_imm(7, 64)); R(2, lambda a, L: t.bcond("lt", a, L["row66"]))
    s(t.mov_lo(0, 6)); bl("CLOSE")
    s("done")
    bl("FINISH")                                          # fix the JPEG's EXIF orientation
    s(t.add_sp(508)); s(t.add_sp(FRAME_SIZE - 508))
    s(t.pop([4, 5, 6, 7], pc=True))

    s("align4")
    s("lit_path87"); s(struct.pack("<I", pix["path87"]))
    s("lit_path66"); s(struct.pack("<I", pix["path66"]))
    s("lit_stride87"); s(struct.pack("<I", 0x48000))
    s("lit_stride66"); s(struct.pack("<I", 0x2000))
    s("k288"); s(struct.pack("<I", 288))
    s("k384"); s(struct.pack("<I", 384))
    s("k768"); s(struct.pack("<I", 768))
    if slots > 255:
        s("k_slots"); s(struct.pack("<I", slots))
        s("k_offset"); s(struct.pack("<I", offset))

    return s.build()


def default_offset(slots: int, next_number: int) -> int:
    """offset such that photo `next_number` goes to slot 0."""
    return (slots - next_number % slots) % slots


def build(slots: int = 10, offset: int = 0):
    # PIC numbers have 4 digits, so more than 10000 slots would never all be used
    if not (1 <= slots <= 10000 and 0 <= offset < slots):
        raise ValueError("slots must be 1..10000 and offset < slots")
    pcode, pl = build_pix(REGION_B[0])
    hcode, hl = build_helpers(REGION_C[0], pl)
    ecode, el = build_exif(REGION_D[0], hl)
    scode, sl = build_sample(REGION_E[0], hl)
    wcode, wl = build_writer(REGION_A[0], pl, {**hl, **el, **sl}, slots, offset)
    if REGION_E[0] + len(scode) > REGION_E[1]:
        raise ValueError(f"region E overflow: {len(scode)} bytes")
    if REGION_D[0] + len(ecode) > REGION_D[1]:
        raise ValueError(f"region D overflow: {len(ecode)} bytes")
    if REGION_C[0] + len(hcode) > REGION_C[1]:
        raise ValueError(f"region C overflow: {len(hcode)} bytes")
    if REGION_B[0] + len(pcode) > REGION_B[1]:
        raise ValueError(f"region B overflow: {len(pcode)} bytes")
    if REGION_A[0] + len(wcode) > REGION_A[1]:
        raise ValueError(f"region A overflow: {len(wcode)} bytes")
    return pcode, pl, wcode, wl, hcode, hl, ecode, el, scode, sl


def slot_patches(body: bytes, slots: int = 10, offset: int = 0) -> list[Patch]:
    pcode, pl, wcode, wl, hcode, hl, ecode, el, scode, sl = build(slots, offset)
    old = lambda a, n: body[a - BASE:a - BASE + n]
    return [
        Patch(REGION_B[0] - BASE, old(REGION_B[0], len(pcode)), pcode),
        Patch(REGION_A[0] - BASE, old(REGION_A[0], len(wcode)), wcode),
        Patch(REGION_C[0] - BASE, old(REGION_C[0], len(hcode)), hcode),
        Patch(REGION_D[0] - BASE, old(REGION_D[0], len(ecode)), ecode),
        Patch(REGION_E[0] - BASE, old(REGION_E[0], len(scode)), scode),
        Patch(DUMP_SKIP - BASE, t.bcond("eq", DUMP_SKIP, DUMP_DONE), NOP),
        Patch(DUMP_CALL - BASE, t.bl(DUMP_CALL, DEBUG_DUMP), t.bl(DUMP_CALL, wl["WRITE_SLOTS"])),
    ]


def main() -> int:
    src, dst = sys.argv[1], sys.argv[2]
    slots = int(sys.argv[3]) if len(sys.argv) > 3 else 10
    next_number = int(sys.argv[4]) if len(sys.argv) > 4 else 0    # next PIC_ number -> slot 0
    offset = default_offset(slots, next_number)
    img = Img1.parse(Path(src).read_bytes())
    patches = pm.build_all(img.body) + slot_patches(img.body, slots, offset)
    body = apply(img.body, patches)
    pcode, pl, wcode, wl, hcode, hl, ecode, el, scode, sl = build(slots, offset)
    print(f"  FINISH/FIX_EXIF {el['FINISH']:#x} ({len(ecode)} of {REGION_D[1]-REGION_D[0]} bytes)")
    print(f"  SETUP/SAMPLE87/SAMPLE66 {sl['SETUP']:#x} ({len(scode)} of {REGION_E[1]-REGION_E[0]} bytes)")
    print(f"  helpers {hl['OPEN_SEEK']:#x} ({len(hcode)} of {REGION_C[1]-REGION_C[0]} bytes)")
    print(f"  PIX {pl['PIX']:#x} ({len(pcode)} of {REGION_B[1]-REGION_B[0]} bytes)")
    print(f"  WRITE_SLOTS {wl['WRITE_SLOTS']:#x} ({len(wcode)} of {REGION_A[1]-REGION_A[0]} bytes), "
          f"slots={slots}, PIC_{next_number:04d} -> slot 0 (offset {offset})")
    Path(dst).write_bytes(Img1.make_unsigned(body, entrypoint=img.header.entrypoint).to_bytes())
    print(f"wrote {dst} ({len(patches)} patches)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
