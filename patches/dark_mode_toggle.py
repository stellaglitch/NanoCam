"""DARK MODE TOGGLE: Settings > General > "Dark Mode" (the old Rotate row) switches the palette.

dark_mode_setting.py only relabels the Rotate row. This patch makes the setting do something:

1. Colour hook. Every UI colour is a 4-byte RGBA `COLR` resource, fetched through
   FUN_081a3f86(manager, type, id) -> pointer to the resource's data. Its last two
   instructions (0x081a3faa: `ldr r0,[sp]; pop {r3-r7,pc}`) become `bl HOOK`. HOOK
   returns the normal pointer unless all of these hold:
       type == 'COLR', the lookup succeeded, id is 0x0dad00xx,
       the preferences object exists, and General.Rotate is on.
   Then, if the id is in the dark palette (dark_theme_palette.COLOR_MAP), it returns a
   pointer to the dark colour instead. Nothing in the resource database changes, so
   with the setting off the UI is exactly stock.

   Backgrounds are bitmaps, not colours (first on-device test: white text on a white
   background). They come through the same getter with type 'BMap', so HOOK also swaps
   the light background bitmaps (LIGHT_BITMAPS) for the stock dark one (DARK_BITMAP)
   by looking that id up instead.

   Menu backgrounds are neither (second on-device test: still white). Menus are table
   elements; the factory FUN_0802c210 looks up COLR <element + 0x50> for the background,
   menus leave that id 0, the lookup fails and the factory stores opaque white in the table.
   The table's draw method is patched to use DARK_BACKGROUND instead of opaque white while
   the setting is on (see TABLE_DRAW_COLOUR). The palette (dark_theme_palette.COLOR_MAP)
   now only turns black text and black image tints light; the white colours it used to
   darken are all text colours.

2. The setting. The row still toggles the General.Rotate preference with its stock
   handler (FUN_08089cb8: prefs->vtable[0x4c] reads a bool, vtable[0x3c] writes it).
   HOOK reads it the same way. The preferences singleton is read straight from its
   slot (0x0855115c) rather than through FUN_0818ed5c, which would create it on first
   use: colours looked up before preferences exist simply stay light.

3. Rotation no longer depends on the setting. The three places that read
   General.Rotate (0x08088308, 0x080b7b60, 0x080bd344: turn-sideways-for-Cover-Flow)
   get `movs r0,#1` in place of `ldrb r0,[r3]`, so they always behave as "Rotate: On".

Space: Nike+ heart-rate-monitor screen controllers (docs/firmware-notes.md section 36). Voice
Memos, the earlier donor, is restored. Those heart-monitor screens must never be opened:
    HOOK           ...Settings_HeartMonitor addon[89]      0x081815d0 .. 0x0818171e (334 bytes)
    tables + DARK  ...HeartMonitorLinking addon[94]        0x08180c2c .. 0x08180d7a (334 bytes)
    NOT_FOUND etc. TTrainer_Cntlr_HeartMonitorLinkingInstructions[98] 0x080a096c .. 0x080a0bc8 (604 bytes)

Not known yet (needs a look on the iPod): screens already on the navigation stack may
keep what they were built with until they're rebuilt, and LIGHT_BITMAPS only lists the
backgrounds we have previews of. Other light bitmaps will stay light until they're added.

Usage:
    python patches/dark_mode_toggle.py firmware/n5g-retailos.dec firmware/n5g-dark-toggle.dfu
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from nanocam import thumb as t  # noqa: E402
from nanocam.img1 import Img1  # noqa: E402
from nanocam.patch import Patch, apply, string_patch_at  # noqa: E402
from nanocam.resources import ResourceDB  # noqa: E402
import dark_mode_setting as dm  # noqa: E402
from dark_theme_palette import COLOR_MAP  # noqa: E402

BASE = 0x07FD1D84

# firmware
GET_RESOURCE = 0x081A3F86       # (manager, type, id) -> data pointer or 0; r6 = type, r7 = id throughout
GET_RESOURCE_TAIL = 0x081A3FAA  # ldr r0,[sp]; pop {r3-r7,pc}
PREFS_SLOT = 0x0855115C         # the preferences singleton (FUN_0818ed5c's [0x08551154 + 8])
KEY_ROTATE = 0x08550BBC         # -> "General.Rotate"
PREFS_GET_BOOL = 0x4C           # vtable offset: get(prefs, key, u8 *out)
ROTATE_READS = (0x08088324, 0x080B7B78, 0x080BD35A)   # ldrb r0,[r3] after each General.Rotate read
VOICE_MEMOS_ENTRY = 0x082003DC  # push {r4,lr} -> bx lr

GET_MANAGER = 0x081A3F7C        # () -> the root resource manager

COLR = 0x434F4C52               # 'COLR'
ID_PREFIX = 0x0DAD00            # every palette id is 0x0dad00xx; the table stores xx

# Bitmaps live on the iPod in Resources/UI/SilverImagesDB.LE.bin and are fetched through the
# same getter with type 'BMap' (e.g. 0x0802a94a). What comes back is the image cache's object.
BMAP = 0x424D6170               # 'BMap'
STR = 0x53747220                # 'Str '
STR_FIRST = 0x0DAD0D8C          # "First" / "Last": the Sort Contacts row's value texts, replaced
STR_LAST = 0x0DAD0D8D           # by the current colour's name (HOOK's 'Str ' branch)
BITMAP_PREFIX = 0x0DAD          # bitmap ids are 0x0dadxxxx; the table stores xxxx
# Light backgrounds (judged from the extracted firmware/slice_*.png previews):
LIGHT_BITMAPS = (
    0x0DAD01DE, 0x0DAD02E5,                 # full-screen white-to-grey gradient (240x356)
    0x0DAD053E, 0x0DAD053F, 0x0DAD0540,     # white list panels, 205 px high
    0x0DAD0553, 0x0DAD0554, 0x0DAD0555,     # white list panels, 176 px high
    0x0DAD0544, 0x0DAD055A,                 # flat light-grey strips (91 / 99 px)
)
DARK_BITMAP = 0x0DAD0572        # stock dark grey-to-black gradient (240x376), used by 9 stock screens

# Status bar. The stock firmware has a silver bar (View 0x0dad1470, on ~255 screens) and a dark
# one (View 0x0dad1471, e.g. Now Playing). They are the same view apart from element ids and
# image sources, so swapping the silver bar's bitmaps for the dark bar's gives a dark bar.
STATUS_BAR_LIGHT = 0x0DAD0129   # 320x20 silver gradient (SORC 0x4c)
STATUS_BAR_DARK = 0x0DAD030C    # 1x20 dark gradient 5e5e5e -> 171717 (SORC 0x51)
# Battery: 0x143..0x159 green-on-silver levels, 0x15a/0x15b charging glyphs; the dark bar's
# white set is the same 25 images 0x19 higher (0x15c..0x174).
BATTERY_LIGHT = (0x0DAD0143, 0x0DAD015B)
BATTERY_DARK = 0x0DAD015C

# (first light id, last light id, dark id, step): light id i -> dark + step * (i - first)
BITMAP_RANGES = [(b, b, DARK_BITMAP, 0) for b in LIGHT_BITMAPS] + [
    (STATUS_BAR_LIGHT, STATUS_BAR_LIGHT, STATUS_BAR_DARK, 0),
    (BATTERY_LIGHT[0], BATTERY_LIGHT[1], BATTERY_DARK, 1),
    (0x0DAD03A0, 0x0DAD03A0, 0x0DAD03A1, 0),    # pedometer shoe: dark grey -> the white one (same size)
    (0x0DAD0304, 0x0DAD0304, 0x0DAD0305, 0),    # shuffle icon (25x17): dark grey -> the white one
    (0x0DAD0311, 0x0DAD0311, 0x0DAD030E, 0),    # status-bar shuffle (18x20): dark -> the dark bar's light one
    # row divider in media lists (cell View 0x0dad1491): 1x2, black 10% + white 40% -> 0x0399, a
    # 240x1 palette strip, black 79%: a 1px near-black line. Untested as a divider (may need 2px height).
    (0x0DAD01A5, 0x0DAD01A5, 0x0DAD0399, 0),
]


def dark_bitmap(bid: int) -> int | None:
    """The bitmap shown instead of `bid` while Dark Mode is on (None: unchanged)."""
    for lo, hi, target, step in BITMAP_RANGES:
        if lo <= bid <= hi:
            return target + step * (bid - lo)
    return None

# donor space
REGION_HOOK = (0x081815D0, 0x0818171E)     # ...Settings_HeartMonitor addon[89] (334 bytes)
REGION_TABLES = (0x08180C2C, 0x08180D7A)   # ...HeartMonitorLinking addon[94] (334 bytes)
REGION_EXTRA = (0x080A096C, 0x080A0BC8)    # TTrainer_Cntlr_HeartMonitorLinkingInstructions[98] (604 bytes)
EXTRA_CODE: list[bytes] = []               # filled by build()

# Menu background. The table factory FUN_0802c210 copies its background colour into the table
# object (4 bytes B,G,R,A at +0x170; opaque white when the COLR lookup fails, as it does for
# menus). The table's draw method (vtable 0x084f604c slot 34, FUN_08058090) passes a pointer to
# those bytes on: `mov r1,r7; adds r1,#0xff; adds r1,#0x71` at 0x08058102. The two adds become
# `bl TABLE_BG`, which does them and then, if the colour is opaque white and Dark Mode is on,
# points r1 at DARK_BACKGROUND instead. Decided at every draw, so menus that already exist
# follow the setting (baking the colour in at creation left them dark after switching off).
TABLE_DRAW_COLOUR = 0x08058104  # adds r1,#0xff; adds r1,#0x71

# Applying the setting at once. Text colours and the status bar are only looked up when a
# screen is (re)built, so after the toggle the open Settings page kept its old colours until
# it was left and re-entered. (First try: call ToggleSetting_FontSize twice from the toggle
# handler. On the iPod only some text refreshed: the font-size observer below compares against
# its cached value, and by the time it ran the font size was back where it started.)
#
# FUN_08185490 is the preference-changed handler (event type 0x16) of the object that provides
# the "large font" flag (source 0xa181, cached at obj+0x78) to every menu table. When
# General.FontSize changes (event id 0x9d2c) and the flag flips, it calls
# obj->vtable[0x64](obj, 'VMax', 0xa181) and the tables rebuild all their rows. Its id check
# (0x0818549e: ldr r1,=0x9d2c; cmp r0,r1) becomes `bl VMAX_HOOK`: when General.Rotate changes
# (event id 0x9d2a, the Dark Mode row's own value source) it flips the cached flag and
# notifies, twice, so the tables rebuild and the flag ends where it was. Then it redoes the
# original comparison.
VMAX_ID_CHECK = 0x0818549E
EVENT_FONT_SIZE = 0x9D2C
EVENT_ROTATE = 0x9D2A
SOURCE_LARGE_FONT = 0xA181
VMAX = 0x564D6178               # 'VMax'

# Selector colour presets (the old Sort Contacts row, relabelled "Highlight").
# The menu selector is not an image. FUN_08093f60(table) asks the table's data provider for a
# selection painter and, when there is none (menus), builds the default one:
# FUN_081c46d0(new(0x14), &c1, &c2, &c3) with three R,G,B,A colours on its stack,
# c1 = 09a4e1 (top), c2 = 0063d3 (bottom), c3 = 96c5da (edge line). The two instructions before
# that call (0x08093fd6: add r1,sp,#0x10; add r3,sp,#8) become `bl SEL_HOOK`, which reorders the
# R,G,B bytes of all three colours according to the stored preset and then does those two adds.
# Reordering channels keeps the gradient and gives six hues: blue, orange, green, pink, teal, purple.
# The preset is stored in General.SortContacts as the string "c0".."c5" (anything else = 0, blue).
# ToggleSetting_SortContacts (FUN_08089cec) is replaced by CYCLE, which stores the next preset.
SEL_MAKE_ARGS = 0x08093FD6

# Cover Flow background. FUN_081aa1e8 renders a Cover Flow frame: it turns a 0..1 brightness
# (1 = the normal white, animated down when leaving for Now Playing) into a grey level 0..255
# and clears with FUN_08252d7c(ctx, 3, grey<<24 | grey<<16 | grey<<8 | 0xff, 1.0, 0). The two
# instructions after the float->int call (0x081aa220: movs r2,#0; str r2,[sp]) become
# `bl CF_HOOK`, which scales the grey level to CF_DARK_LEVEL/256 while Dark Mode is on.
CF_CLEAR_GREY = 0x081AA220
CF_DARK_LEVEL = 0x24            # white 255 -> 0x23, about the menu background 242424
SORT_TOGGLE = 0x08089CEC        # push {r3-r7,lr}; ... (10 bytes replaced after the push)
KEY_SORT = 0x08550BC0           # -> "General.SortContacts"
EVENT_SORT = 0x9D2D             # its change id (the row's value SORC 0x994)
GET_PREFS = 0x0827F4E4          # () -> preferences, created if needed
PREFS_GET_STR = 0x50            # vtable: get(prefs, key, char **out)
PREFS_SET_STR = 0x40            # vtable: set(prefs, key, char *value, 0)
SEL_PERMS = [(0, 1, 2), (2, 1, 0), (1, 2, 0), (2, 0, 1), (0, 2, 1), (1, 0, 2), (2, 0, 0)]   # source byte for R, G, B
SEL_NAMES = ["Blue", "Orange", "Green", "Pink", "Teal", "Purple", "Red"]   # one per SEL_PERMS entry
# Red = (2, 0, 0): R from the blue channel, G and B from the (low) red channel:
# 09a4e1 -> e10909, 0063d3 -> d30000, 96c5da -> da9696.
STR_SORT_LABEL = 0x0DAD0D6F     # "Sort Contacts"; HOOK's 'Str ' branch returns SORT_LABEL instead
SORT_LABEL = "Highlight Color"
DARK_BACKGROUND = "242424ff"    # RGBA, like a COLR resource (121212 was too dark, 363636 too light)

# Cover Flow reflections. FUN_080dfbb4 (the 3D scene) draws the cover quad with FUN_080f0682 and,
# at 0x080dfffe, the reflection with FUN_080ebf18 (a second texture unit holds the fade, and its
# texture-env constant is the fade alpha). That call becomes `bl REFL_SKIP`, which skips the
# reflection while Dark Mode is on (stock Cover Flow fades to white, which looks wrong on dark).
REFL_DRAW = 0x080EBF18
REFL_CALL = 0x080DFFFE
# The same function draws the cover plane with FUN_080f0682(&scene[0x60], ctx, p3) at 0x080dfe64. While an
# album is opened (scene[0x60] == scene[0x68] != 0) that plane is the album's white back face, which
# shows as a white box under the track list; PLANE_SKIP skips it with Dark Mode on.
PLANE_DRAW = 0x080F0682
PLANE_CALL = 0x080DFE64
SET_COLOUR = 0x08273A1C          # glColor4f wrapper (r, g, b, a floats)

# `list` elements (Cover Flow's flip-side track list and 15 more views) carry their selection colours
# inline. FUN_0802b8e4 builds the list and turns element words +0x74..+0x90 into colour objects with
# FUN_081b2100(dst, argb). The first four (gradient top/bottom, two edge colours) go through PERMCOL.
LIST_COLOUR = 0x081B2100
LIST_COLOUR_CALLS = (0x0802BA6A, 0x0802BA80, 0x0802BA96, 0x0802BAAE)
LIST_COLOUR_SET = 0x081B2110     # FUN_081b2110(dst, colour object): assigns it (used for the panel at +0x7c)
TPL_MEMCPY_CALLS = (0x0802BBD8, 0x0802BBFC)   # blx memcpy of the two row-layer templates
TPL_COLOUR = 0xFF2A2A2A
LIST_BG_SITE = 0x0802B9CE        # `ldr r0,[sp,#0x258]; ldr r1,[r5,#0x30]`, the common point after the COLR path

POP_RET = t.pop([3, 4, 5, 6, 7], pc=True)   # GET_RESOURCE's own epilogue


def build_tables(base: int) -> tuple[bytes, dict[str, int]]:
    """The lookup tables, plus DARK() (is the setting on?), which the hook calls.

    colors: 4 bytes RGBA each (word-aligned, like the real resources)
    ids:    the colours' id low bytes, 0-terminated
    """
    for cid in COLOR_MAP:
        if cid >> 8 != ID_PREFIX or cid & 0xFF == 0:
            raise ValueError(f"COLR {cid:#x} isn't 0x0dad00xx; the id table can't hold it")
    s = t.Asm(base)
    R = s.ref
    lit = lambda rd, name: R(2, lambda a, L: t.ldr_pc(a, rd, L[name]))
    s("colors"); s(b"".join(bytes.fromhex(v) for v in COLOR_MAP.values()))
    s("ids"); s(bytes(cid & 0xFF for cid in COLOR_MAP) + b"\0")
    s("align4")

    # DARK() -> r0 = 1 if the Dark Mode setting is on (0 if preferences don't exist yet). Clobbers r1-r3.
    s("DARK")
    s(t.push([1, 2, 3], lr=True))                                  # 3 scratch words; [sp] = the bool
    lit(1, "k_prefs"); s(t.ldr_imm(0, 1, 0)); s(t.cmp_imm(0, 0))
    R(2, lambda a, L: t.bcond("eq", a, L["dark_out"]))
    s(t.movs_imm(3, 0)); s(t.str_sp(3, 0))
    s(t.add_sp_rd(2, 0))
    lit(1, "k_key"); s(t.ldr_imm(1, 1, 0))
    s(t.ldr_imm(3, 0, 0)); s(t.ldr_imm(3, 3, PREFS_GET_BOOL)); s(t.blx_reg(3))   # get_bool(prefs, key, &on)
    s(t.ldr_sp(0, 0))
    s("dark_out")
    s(t.pop([1, 2, 3], pc=True))

    # LISTBG: replaces `ldr r0,[sp,#0x258]; ldr r1,[r5,#0x30]` at LIST_BG_SITE in the `list` element factory
    # FUN_0802b8e4 (where the colour-resource path has just finished). For Cover Flow's two track lists, with
    # Dark Mode on, it does what that path does for a colour: sets the background panel's colour to dark grey.
    # sp is 4 lower inside the hook (the pushed lr), so frame offsets are +4: element [sp,#0x25c], panel
    # [sp,#0x194], a scratch colour object at sp+0xd0.
    s("LISTBG")
    s(t.push([], lr=True))
    s(t.ldr_sp(0, 0x25C)); s(t.ldr_imm(1, 0, 0x30))
    lit(2, "k_lid1"); s(t.cmp_reg(1, 2)); R(2, lambda a, L: t.bcond("eq", a, L["lb_go"]))
    lit(2, "k_lid2"); s(t.cmp_reg(1, 2)); R(2, lambda a, L: t.bcond("ne", a, L["lb_out"]))
    s("lb_go")
    R(4, lambda a, L: t.bl(a, L["DARK"]))
    s(t.cmp_imm(0, 0)); R(2, lambda a, L: t.bcond("eq", a, L["lb_out"]))
    s(t.ldr_sp(0, 0x194)); s(t.movs_imm(2, 7)); s(t.lsls_imm(2, 2, 15))
    s(t.ldr_imm(1, 0, 0x30)); s(t.orrs(1, 2)); s(t.str_imm(1, 0, 0x30))
    s(t.add_sp_rd(0, 0xD0)); lit(1, "k_listbg")
    R(4, lambda a, L: t.bl(a, LIST_COLOUR))
    s(t.ldr_sp(0, 0x194)); s(t.add_sp_rd(1, 0xD0)); s(t.adds_imm(0, 0x7C))
    R(4, lambda a, L: t.bl(a, LIST_COLOUR_SET))
    s("lb_out")
    s(t.ldr_sp(0, 0x25C)); s(t.ldr_imm(1, 5, 0x30))
    s(t.pop([], pc=True))
    s("align4")
    s("k_lid1"); s(struct.pack("<I", 0x0DAD1E06))
    s("k_lid2"); s(struct.pack("<I", 0x0DAD1E0C))
    s("k_listbg"); s(struct.pack("<I", 0xFF242424))

    # TPLCOPY: stands in for the `blx memcpy(dst, template, 0x60)` that copies a row-layer template onto the
    # stack in the list factory. After the copy, with Dark Mode on, the layer's colour word (+0xc, white)
    # is set to dark grey. (Patching the template data in the image made the iPod boot stock firmware.)
    s("TPLCOPY")
    s(t.push([4], lr=True)); s(t.mov_lo(4, 0))
    lit(3, "k_memcpy"); s(t.blx_reg(3))
    R(4, lambda a, L: t.bl(a, L["DARK"]))
    s(t.cmp_imm(0, 0)); R(2, lambda a, L: t.bcond("eq", a, L["tc_out"]))
    lit(1, "k_tpl"); s(t.str_imm(1, 4, 0xC))
    s("tc_out")
    s(t.pop([4], pc=True))
    s("align4")
    s("k_memcpy"); s(struct.pack("<I", 0x082002C4))
    s("k_tpl"); s(struct.pack("<I", TPL_COLOUR))
    s("align4")
    s("k_prefs"); s(struct.pack("<I", PREFS_SLOT))
    s("k_key"); s(struct.pack("<I", KEY_ROTATE))
    return s.build()


def build_extra(base: int, tables: dict[str, int]) -> tuple[bytes, dict[str, int]]:
    """NOT_FOUND (HOOK's exit for a failed lookup), TABLE_BG (see TABLE_DRAW_COLOUR) and the
    bitmap table."""
    s = t.Asm(base)
    R = s.ref
    lit = lambda rd, name: R(2, lambda a, L: t.ldr_pc(a, rd, L[name]))
    br = lambda cond, name: R(2, lambda a, L: t.bcond(cond, a, L[name]))

    s("NOT_FOUND")
    s(t.movs_imm(0, 0))
    s(POP_RET)

    # TABLE_BG: r1 = table object -> r1 = pointer to its background colour. r0 is free (the
    # caller sets it next); r2-r7 are preserved.
    s("TABLE_BG")
    s(t.adds_imm(1, 0xFF)); s(t.adds_imm(1, 0x71))                  # the two replaced instructions
    s(t.push([4], lr=True))
    s(t.ldr_imm(0, 1, 0)); s(t.adds_imm(0, 1)); br("ne", "tb_out")  # not opaque white: leave it
    s(t.mov_lo(4, 1))                                               # DARK returns its result through r1's slot
    R(4, lambda a, L: t.bl(a, tables["DARK"])); s(t.mov_lo(1, 4)); s(t.cmp_imm(0, 0)); br("eq", "tb_out")
    lit(1, "k_bg")
    s("tb_out")
    s(t.pop([4], pc=True))

    # REFL_SKIP: stands in for `bl REFL_DRAW` (r0-r3 = its arguments).
    s("REFL_SKIP")
    s(t.push([4], lr=True)); s(t.mov_lo(4, 0))
    R(4, lambda a, L: t.bl(a, tables["DARK"]))                       # keeps r1-r3
    s(t.cmp_imm(0, 0)); br("ne", "rs_out")
    s(t.mov_lo(0, 4))
    R(4, lambda a, L: t.bl(a, REFL_DRAW))
    s("rs_out")
    s(t.pop([4], pc=True))
    # VMAX_HOOK: see VMAX_ID_CHECK. In: r0 = the changed preference's event id, r4 = the object.
    # Out: flags of `cmp r0, #EVENT_FONT_SIZE`, r0 and r4-r7 unchanged.
    s("VMAX_HOOK")
    s(t.push([0, 6], lr=True))
    lit(1, "k_ev_rotate"); s(t.cmp_reg(0, 1)); br("eq", "vm_go")
    lit(1, "k_ev_sort"); s(t.cmp_reg(0, 1)); br("ne", "vm_done")
    s("vm_go")
    s(t.movs_imm(6, 2))
    s("vm_loop")
    s(t.mov_lo(1, 4)); s(t.adds_imm(1, 0x60))
    s(t.ldrb(0, 1, 0x18)); s(t.movs_imm(2, 1)); s(struct.pack("<H", 0x4050))   # eors r0, r2
    s(t.strb(0, 1, 0x18))
    s(t.ldr_imm(0, 4, 0)); lit(2, "k_src"); lit(1, "k_vmax"); s(t.ldr_imm(3, 0, 0x64))
    s(t.mov_lo(0, 4)); s(t.blx_reg(3))
    s(t.subs_imm(6, 1)); br("ne", "vm_loop")
    s("vm_done")
    s(t.ldr_sp(0, 0)); lit(1, "k_ev_font"); s(t.cmp_reg(0, 1))
    s(t.pop([0, 6], pc=True))

    # PRESET() -> r0 = selector preset 0..5. Clobbers r1-r3.
    s("PRESET")
    s(t.push([4], lr=True)); s(t.sub_sp(8))
    lit(1, "k_prefs_slot"); s(t.ldr_imm(0, 1, 0)); s(t.cmp_imm(0, 0)); br("eq", "pr_zero")
    s(t.movs_imm(3, 0)); s(t.str_sp(3, 0))
    lit(1, "k_key_sort"); s(t.ldr_imm(1, 1, 0)); s(t.add_sp_rd(2, 0))
    s(t.ldr_imm(3, 0, 0)); s(t.ldr_imm(3, 3, PREFS_GET_STR)); s(t.blx_reg(3))
    s(t.ldr_sp(0, 0)); s(t.cmp_imm(0, 0)); br("eq", "pr_zero")
    s(t.ldrb(1, 0, 0)); s(t.cmp_imm(1, ord("c"))); br("ne", "pr_zero")
    s(t.ldrb(0, 0, 1)); s(t.subs_imm(0, ord("0"))); s(t.cmp_imm(0, len(SEL_PERMS))); br("lo", "pr_out")
    s("pr_zero")
    s(t.movs_imm(0, 0))
    s("pr_out")
    s(t.add_sp(8)); s(t.pop([4], pc=True))

    # SEL_HOOK: see SEL_MAKE_ARGS. In: sp = FUN_08093f60's frame (colours at sp+8, +0xc, +0x10),
    # r0 and r2 are arguments already set. Out: r1 = sp+0x10, r3 = sp+8; r0, r2, r4-r7 unchanged.
    s("SEL_HOOK")
    s(t.push([0, 2, 4, 5, 6, 7], lr=True)); s(t.sub_sp(4))            # 32 bytes below the caller's sp
    R(4, lambda a, L: t.bl(a, L["PRESET"])); s(t.cmp_imm(0, 0)); br("eq", "sel_done")
    s(t.lsls_imm(1, 0, 1)); s(t.adds_reg(0, 0, 1)); lit(4, "k_perms"); s(t.adds_reg(4, 4, 0))
    s(t.add_sp_rd(6, 32 + 8)); s(t.movs_imm(5, 3))
    s("sel_loop")
    s(t.ldr_imm(3, 6, 0)); s(t.str_sp(3, 0)); s(t.add_sp_rd(7, 0))    # a copy to read from
    for j in range(3):
        s(t.ldrb(0, 4, j)); s(t.ldrb_reg(0, 7, 0)); s(t.strb(0, 6, j))
    s(t.adds_imm(6, 4)); s(t.subs_imm(5, 1)); br("ne", "sel_loop")
    s("sel_done")
    s(t.add_sp(4))
    s(t.add_sp_rd(1, 28 + 0x10)); s(t.add_sp_rd(3, 28 + 8))          # the two replaced instructions
    s(t.pop([0, 2, 4, 5, 6, 7], pc=True))

    # CF_HOOK: see CF_CLEAR_GREY. In/out: r0 = grey level. Also does the two replaced instructions.
    s("CF_HOOK")
    s(t.push([4], lr=True)); s(t.mov_lo(4, 0))
    R(4, lambda a, L: t.bl(a, tables["DARK"])); s(t.cmp_imm(0, 0)); br("eq", "cf_out")
    s(t.movs_imm(1, CF_DARK_LEVEL)); s(t.muls(4, 1)); s(t.lsrs_imm(4, 4, 8))
    s("cf_out")
    s(t.mov_lo(0, 4)); s(t.movs_imm(2, 0)); s(t.str_sp(2, 8))        # the caller's [sp]
    s(t.pop([4], pc=True))

    # CYCLE: body of the old Sort Contacts toggle. Stores the next preset.
    s("CYCLE")
    s(t.push([4], lr=True))
    R(4, lambda a, L: t.bl(a, L["PRESET"]))
    s(t.adds_imm(0, 1)); s(t.cmp_imm(0, len(SEL_PERMS))); br("lo", "cy_ok"); s(t.movs_imm(0, 0))
    s("cy_ok")
    s(t.lsls_imm(4, 0, 2))
    R(4, lambda a, L: t.bl(a, GET_PREFS))
    lit(1, "k_key_sort"); s(t.ldr_imm(1, 1, 0)); lit(2, "k_names"); s(t.adds_reg(2, 2, 4))
    s(t.movs_imm(3, 0)); s(t.ldr_imm(4, 0, 0)); s(t.ldr_imm(4, 4, PREFS_SET_STR)); s(t.blx_reg(4))
    s(t.pop([4], pc=True))

    s("align4")
    s("k_prefs_slot"); s(struct.pack("<I", PREFS_SLOT))
    s("k_key_sort"); s(struct.pack("<I", KEY_SORT))
    s("k_perms"); R(4, lambda a, L: struct.pack("<I", L["perms"]))
    s("k_names"); R(4, lambda a, L: struct.pack("<I", L["names"]))
    s("k_ev_sort"); s(struct.pack("<I", EVENT_SORT))
    s("names"); s(b"".join(b"c%d\0\0" % i for i in range(len(SEL_PERMS))))
    s("cnames"); s(b"".join(n.encode().ljust(8, b"\0") for n in SEL_NAMES))   # 8-byte slots, indexed by preset
    s("label"); s(SORT_LABEL.encode() + b"\0"); s("align4")
    s("perms"); s(bytes(x for p in SEL_PERMS for x in p)); s("align4")
    s("k_ev_rotate"); s(struct.pack("<I", EVENT_ROTATE))
    s("k_ev_font"); s(struct.pack("<I", EVENT_FONT_SIZE))
    s("k_src"); s(struct.pack("<I", SOURCE_LARGE_FONT))
    s("k_vmax"); s(struct.pack("<I", VMAX))
    s("k_bg"); R(4, lambda a, L: struct.pack("<I", L["bg"]))
    rgba = bytes.fromhex(DARK_BACKGROUND)
    s("bg"); s(bytes([rgba[2], rgba[1], rgba[0], rgba[3]]))          # the table object's order: B,G,R,A
    # bitmaps: BITMAP_RANGES as 4 halfwords each (ids' low halves), 0-terminated
    s("bitmaps")
    for lo, hi, target, step in BITMAP_RANGES:
        if any(b >> 16 != BITMAP_PREFIX or b & 0xFFFF == 0 for b in (lo, hi, target)):
            raise ValueError(f"bitmap range {lo:#x}..{hi:#x} -> {target:#x} isn't 0x0dadxxxx")
        if dark_bitmap(target) is not None or dark_bitmap(target + step * (hi - lo)) is not None:
            raise ValueError(f"dark bitmap {target:#x} is itself in a light range (would recurse)")
        s(struct.pack("<4H", lo & 0xFFFF, hi & 0xFFFF, target & 0xFFFF, step))
    s(struct.pack("<H", 0))
    return s.build()


def build_hook(base: int, tables: dict[str, int], extra: dict[str, int]) -> tuple[bytes, dict[str, int]]:
    """HOOK: reached by `bl` from GET_RESOURCE's tail, with that function's frame still pushed
    (r6 = type, r7 = id, [sp] = the pointer it found). Always leaves through that frame's pop."""
    s = t.Asm(base)
    R = s.ref
    lit = lambda rd, name: R(2, lambda a, L: t.ldr_pc(a, rd, L[name]))
    br = lambda cond, name: R(2, lambda a, L: t.bcond(cond, a, L[name]))
    bl = lambda target: R(4, lambda a, L: t.bl(a, target))

    s("HOOK")
    s(t.ldr_sp(0, 0)); s(t.cmp_imm(0, 0)); br("ne", "have")
    bl(extra["NOT_FOUND"])                                           # lookup failed; doesn't come back
    s("have")
    lit(1, "k_colr"); s(t.cmp_reg(6, 1)); br("eq", "colour")
    lit(1, "k_str"); s(t.cmp_reg(6, 1)); br("eq", "string")
    lit(1, "k_bmap"); s(t.cmp_reg(6, 1)); br("eq", "bitmap")
    R(2, lambda a, L: t.b(a, L["out"]))                              # neither a colour, a string nor a bitmap

    # ---- string: the Highlight Color row's label, and its value ("First"/"Last" -> colour name) ----
    s("string")
    lit(1, "k_label_id"); s(t.cmp_reg(7, 1)); br("eq", "s_label")
    lit(1, "k_first_id"); s(t.cmp_reg(7, 1)); br("eq", "s_value")
    lit(1, "k_last_id"); s(t.cmp_reg(7, 1)); br("ne", "out")
    s("s_value")
    bl(extra["PRESET"])                                              # r0 = preset; clobbers r1-r3 only
    s(t.lsls_imm(0, 0, 3)); lit(1, "k_cnames"); s(t.adds_reg(0, 0, 1))
    s(POP_RET)
    s("s_label")
    lit(0, "k_labelp")
    s(POP_RET)

    # ---- bitmap: a light background -> the stock dark background ---------------------
    s("bitmap")
    s(t.lsrs_imm(1, 7, 16)); lit(2, "k_bprefix"); s(t.cmp_reg(1, 2)); br("ne", "out")
    bl(tables["DARK"]); s(t.cmp_imm(0, 0)); br("eq", "out")
    s(t.lsls_imm(1, 7, 16)); s(t.lsrs_imm(1, 1, 16))
    lit(2, "k_bitmaps")
    s("bnext")
    s(t.ldrh_imm(0, 2, 0)); s(t.cmp_imm(0, 0)); br("eq", "out")     # end of table: not a light bitmap
    s(t.cmp_reg(1, 0)); br("lo", "bskip")
    s(t.ldrh_imm(3, 2, 2)); s(t.cmp_reg(1, 3)); br("ls", "bfound")
    s("bskip")
    s(t.adds_imm(2, 8)); R(2, lambda a, L: t.b(a, L["bnext"]))
    s("bfound")                                                      # dark id = target + step * (id - first)
    s(t.subs_reg(1, 1, 0)); s(t.ldrh_imm(3, 2, 6)); s(t.muls(1, 3))
    s(t.ldrh_imm(3, 2, 4)); s(t.adds_reg(1, 1, 3))
    s(t.lsrs_imm(3, 7, 16)); s(t.lsls_imm(3, 3, 16)); s(t.adds_reg(7, 1, 3))   # r7 (restored by the pop)
    # look the dark bitmap up instead. Dark ids are never in a light range, so this doesn't recurse
    # again. The result is that bitmap's own cache object (it carries its own id at +0x18), so the
    # caller's retain/release stay consistent even if the setting changes while it's held.
    bl(GET_MANAGER)
    s(t.mov_lo(1, 6)); s(t.mov_lo(2, 7))
    bl(GET_RESOURCE)
    s(t.cmp_imm(0, 0)); br("eq", "out")                              # not found: keep the light one
    s(POP_RET)

    # ---- colour: a mapped id -> the dark palette entry -------------------------------
    s("colour")
    s(t.lsrs_imm(1, 7, 8)); lit(2, "k_prefix"); s(t.cmp_reg(1, 2)); br("ne", "out")
    bl(tables["DARK"]); s(t.cmp_imm(0, 0)); br("eq", "out")
    s(t.lsls_imm(1, 7, 24)); s(t.lsrs_imm(1, 1, 24))
    lit(2, "k_ids"); s(t.movs_imm(3, 0))
    s("next")
    s(t.ldrb_reg(0, 2, 3)); s(t.cmp_imm(0, 0)); br("eq", "out")     # end of table: keep the stock colour
    s(t.cmp_reg(0, 1)); br("eq", "found")
    s(t.adds_imm(3, 1)); R(2, lambda a, L: t.b(a, L["next"]))
    s("found")
    s(t.lsls_imm(3, 3, 2)); lit(0, "k_colors"); s(t.adds_reg(0, 0, 3))
    s(POP_RET)
    s("out")
    s(t.ldr_sp(0, 0))
    s(POP_RET)

    # PERMCOL: stands in for `bl LIST_COLOUR` (FUN_081b2100(dst, argb), r0 = dst, r1 = the word B,G,R,A
    # in memory order) at the first four colours of a `list` element (its selection gradient and edges).
    # Channels are reordered like SEL_HOOK does for menus. Returns what LIST_COLOUR returns.
    s("PERMCOL")
    s(t.push([4, 5, 6, 7], lr=True)); s(t.sub_sp(8))
    s(t.mov_lo(5, 0)); s(t.mov_lo(6, 1))
    bl(extra["PRESET"])                                              # r0 = preset 0..; clobbers r1-r3
    s(t.lsls_imm(1, 0, 1)); s(t.adds_reg(0, 0, 1)); lit(4, "k_permsx"); s(t.adds_reg(4, 4, 0))
    s(t.str_sp(6, 0)); s(t.str_sp(6, 4))                             # [sp] = in, [sp+4] = out
    for j in range(3):
        s(t.ldrb(2, 4, j)); s(t.movs_imm(3, 2)); s(t.subs_reg(3, 3, 2))   # r3 = byte index of source channel
        s(t.add_sp_rd(1, 0)); s(t.ldrb_reg(2, 1, 3))
        s(t.add_sp_rd(1, 4)); s(t.strb(2, 1, 2 - j))
    s(t.ldr_sp(1, 4)); s(t.mov_lo(0, 5))
    bl(LIST_COLOUR)
    s(t.add_sp(8)); s(t.pop([4, 5, 6, 7], pc=True))
    s("align4")
    s("k_permsx"); s(struct.pack("<I", extra["perms"]))
    s("k_colr"); s(struct.pack("<I", COLR))
    s("k_bmap"); s(struct.pack("<I", BMAP))
    s("k_str"); s(struct.pack("<I", STR))
    s("k_label_id"); s(struct.pack("<I", STR_SORT_LABEL))
    s("k_first_id"); s(struct.pack("<I", STR_FIRST))
    s("k_last_id"); s(struct.pack("<I", STR_LAST))
    s("k_cnames"); s(struct.pack("<I", extra["cnames"]))
    s("k_labelp"); s(struct.pack("<I", extra["label"]))
    s("k_prefix"); s(struct.pack("<I", ID_PREFIX))
    s("k_bprefix"); s(struct.pack("<I", BITMAP_PREFIX))
    s("k_ids"); s(struct.pack("<I", tables["ids"]))
    s("k_colors"); s(struct.pack("<I", tables["colors"]))
    s("k_bitmaps"); s(struct.pack("<I", extra["bitmaps"]))
    return s.build()


def build():
    tcode, tl = build_tables(REGION_TABLES[0])
    ecode, el = build_extra(REGION_EXTRA[0], tl)
    hcode, hl = build_hook(REGION_HOOK[0], tl, el)
    tl = {**tl, **el}
    if REGION_EXTRA[0] + len(ecode) > REGION_EXTRA[1]:
        raise ValueError(f"extra region overflow: {len(ecode)} bytes")
    EXTRA_CODE[:] = [ecode]
    if REGION_TABLES[0] + len(tcode) > REGION_TABLES[1]:
        raise ValueError(f"table region overflow: {len(tcode)} bytes (too many colours)")
    if REGION_HOOK[0] + len(hcode) > REGION_HOOK[1]:
        raise ValueError(f"hook region overflow: {len(hcode)} bytes")
    return hcode, hl, tcode, tl


def toggle_patches(body: bytes, cut_voice_memos: bool = False) -> list[Patch]:
    """The hook, its tables and the rotation overrides. Pass cut_voice_memos=False when
    photos_slot.slot_patches is applied too (it already cuts the Voice Memos entry)."""
    db = ResourceDB(body)
    for cid in COLOR_MAP:
        if db.get("COLR", cid) is None:
            raise ValueError(f"COLR {cid:#x} not in this firmware")
    hcode, hl, tcode, tl = build()
    old = lambda a, n: body[a - BASE:a - BASE + n]
    ecode = EXTRA_CODE[0]
    patches = [
        Patch(REGION_EXTRA[0] - BASE, old(REGION_EXTRA[0], len(ecode)), ecode),
        Patch(REGION_TABLES[0] - BASE, old(REGION_TABLES[0], len(tcode)), tcode),
        Patch(REGION_HOOK[0] - BASE, old(REGION_HOOK[0], len(hcode)), hcode),
        Patch(GET_RESOURCE_TAIL - BASE, t.ldr_sp(0, 0) + POP_RET, t.bl(GET_RESOURCE_TAIL, hl["HOOK"])),
    ]
    patches.append(Patch(TABLE_DRAW_COLOUR - BASE, t.adds_imm(1, 0xFF) + t.adds_imm(1, 0x71),
                         t.bl(TABLE_DRAW_COLOUR, tl["TABLE_BG"])))
    # stock: ldr r1, [pc, #0x44] (=0x9d2c); cmp r0, r1
    # stock: add r1,sp,#0x10; add r3,sp,#8
    patches.append(Patch(SEL_MAKE_ARGS - BASE, t.add_sp_rd(1, 0x10) + t.add_sp_rd(3, 8),
                         t.bl(SEL_MAKE_ARGS, tl["SEL_HOOK"])))
    # ToggleSetting_SortContacts: keep its push, then bl CYCLE; movs r0,#1; pop {r3-r7,pc}
    patches.append(Patch(SORT_TOGGLE + 2 - BASE, bytes.fromhex("f5f1f9fb0168104c"),
                         t.bl(SORT_TOGGLE + 2, tl["CYCLE"]) + t.movs_imm(0, 1) + t.pop([3, 4, 5, 6, 7], pc=True)))
    patches.append(Patch(LIST_BG_SITE - BASE, t.ldr_sp(0, 0x258) + t.ldr_imm(1, 5, 0x30),
                         t.bl(LIST_BG_SITE, tl["LISTBG"])))
    # (Tried and removed: setting the Cover Flow track list's COLR word (word 6 after its 'list' tag, to
    # COLR 0x2b) crashed the iPod when the menu opened. The list's white panel is still unsolved.)
    # Notes instructions page (View 0x0dad1540: no background of its own, so the window's white shows).
    # Its first element is the same 6px black bar as in menus (an `imag` with SORC 0, tint COLR 0x28,
    # 240 wide, 6 high, anchored to the bottom). Make it as tall as the page (0x164 = 356) and tint it
    # COLR 0x2b (white, unused elsewhere; mapped to the menu grey in dark_theme_palette), so the page gets
    # a solid background. (Tried before: fill frame 0x7ffffffe + a bitmap SORC; nothing drew. Per-view
    # tint changes do work: the calendar bars below showed magenta in a diagnostic build.)
    nv = db.get("View", 0x0DAD1540)
    for idx, old, new in ((6, 6, 0x164), (23, 0x0DAD0028, 0x0DAD002B)):   # confirmed on the iPod: this height + a mapped tint fills the page
        off = nv.offset + 4 * idx
        patches.append(Patch(off, struct.pack("<I", old), struct.pack("<I", new)))
    # The same 6px bar in every other view (calendar, clock, stopwatch, contacts...) sits on that app's own
    # background, which Dark Mode doesn't change, so a dark bar stands out. A tint with alpha 1 still drew
    # solid black, alpha 0 counts as no tint, and height 0 left the bar in place (probably "auto"), so the
    # bar's height goes from 6 to 1 instead (in both modes). (The magenta diagnostic build confirmed
    # per-view edits are applied.)
    for v in db.by_type["View"]:
        if v.id in (0x0DAD1474, 0x0DAD1540) or v.size % 4:
            continue
        vw = struct.unpack(f"<{v.size // 4}I", v.data(body))
        for i in range(14, len(vw) - 16):
            if (vw[i] == 0x696D6167 and vw[i + 1] == 0x10000 and vw[i + 6] == 0x0DAD0028 and vw[i + 15] == 0
                    and vw[i - 11] == 6 and vw[i - 8] == 0xF0):
                patches.append(Patch(v.offset + 4 * (i - 11), struct.pack("<I", 6), struct.pack("<I", 1)))
    for site in LIST_COLOUR_CALLS:
        patches.append(Patch(site - BASE, t.bl(site, LIST_COLOUR), t.bl(site, hl["PERMCOL"])))
    # PLANE_DARK (off-screen plane) rejected: the album vanishes and the list pops in. Not applied.
    # Diagnostic: the two row-layer templates of the `list` factory (colour word +0xc, white): red / green.
    # (Removed: patching these two words made the iPod boot stock firmware, no Dark Mode or camera.)
    # TPLCOPY (row-layer template word +0xc) not applied: it is probably a -1 "none" handle, not a colour, and
    # changing it made the iPod boot stock firmware.
    patches.append(Patch(REFL_CALL - BASE, t.bl(REFL_CALL, REFL_DRAW), t.bl(REFL_CALL, tl["REFL_SKIP"])))
    patches.append(Patch(CF_CLEAR_GREY - BASE, t.movs_imm(2, 0) + t.str_sp(2, 0), t.bl(CF_CLEAR_GREY, tl["CF_HOOK"])))
    patches.append(Patch(VMAX_ID_CHECK - BASE, bytes.fromhex("11498842"), t.bl(VMAX_ID_CHECK, tl["VMAX_HOOK"])))
    patches += [Patch(a - BASE, t.ldrb(0, 3), t.movs_imm(0, 1)) for a in ROTATE_READS]
    if cut_voice_memos:
        patches.append(Patch(VOICE_MEMOS_ENTRY - BASE, bytes.fromhex("10b5"), t.bx(14)))
    return patches


def build_patches(body: bytes, cut_voice_memos: bool = False) -> list[Patch]:
    """Everything for Dark Mode: the relabelled row plus the working toggle."""
    return dm.build_patches(body) + toggle_patches(body, cut_voice_memos)


def main() -> int:
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <retailos.dec> <output.dfu>", file=sys.stderr)
        return 1
    img = Img1.parse(Path(sys.argv[1]).read_bytes())
    patches = build_patches(img.body)
    body = apply(img.body, patches)
    hcode, hl, tcode, tl = build()
    print(f"  HOOK {hl['HOOK']:#x} ({len(hcode)} of {REGION_HOOK[1] - REGION_HOOK[0]} bytes)")
    print(f"  NOT_FOUND {tl['NOT_FOUND']:#x} ({len(EXTRA_CODE[0])} of {REGION_EXTRA[1] - REGION_EXTRA[0]} bytes)")
    print(f"  tables {tl['colors']:#x} ({len(tcode)} of {REGION_TABLES[1] - REGION_TABLES[0]} bytes, "
          f"{len(COLOR_MAP)} colours, {len(BITMAP_RANGES)} bitmap ranges)")
    Path(sys.argv[2]).write_bytes(Img1.make_unsigned(body, entrypoint=img.header.entrypoint).to_bytes())
    print(f"wrote {sys.argv[2]} ({len(patches)} patches)")
    return 0


if __name__ == "__main__":
    sys.exit(main())





