"""Generate an Always-On Dark Mode test build by inverting the UI theme palette.

Changes:
1. Replaces pure white (0xffffffff) backgrounds / highlights in the UI theme palette
   with dark gray/black (0x1e1e1eff / 0x121212ff).
2. Replaces primary black text (0x000000ff) with crisp white/light text (0xffffffff / 0xf0f0f0ff).
3. Adjusts dark grays to light grays for secondary labels and subtitles.

All changes are in-place 4-byte RGBA COLR resource edits.
No code, table layouts, or event scripts are touched.

Usage:
    .\\.venv\\Scripts\\python.exe patches/dark_theme_palette.py firmware/n5g-retailos.dec firmware/n5g-dark-theme.dfu
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nanocam.img1 import Img1
from nanocam.patch import Patch, apply
from nanocam.resources import ResourceDB


# The dark palette: COLR resource ID -> new RGBA. Also used by dark_mode_toggle.py,
# which applies it at run time only while the Dark Mode setting is on.
COLOR_MAP = {
    # Primary Text: Black -> White
    0x0DAD0013: "ffffffff",
    0x0DAD0037: "f0f0f0ff",
    0x0DAD004E: "e5e5e5ff",
    0x0DAD0055: "f0f0f0ff",
    0x0DAD0070: "f0f0f0ff",
    0x0DAD0076: "f0f0f0ff",
    0x0DAD0086: "f0f0f0ff",
    0x0DAD0087: "f0f0f0ff",
    0x0DAD0088: "f0f0f0ff",
    0x0DAD009F: "f0f0f0ff",
    0x0DAD00A5: "f0f0f0ff",
    0x0DAD0046: "f0f0f0ff",
    0x0DAD005D: "f0f0f0ff",
    0x0DAD006E: "f0f0f0ff",
    # Cover Flow title / artist (View 0x0dad14cc), now that its background goes dark too
    0x0DAD003F: "f0f0f0ff",
    # Cover Flow track list: song titles and times (found by recolouring candidates and photographing the screen)
    0x0DAD0040: "f0f0f0ff",
    0x0DAD0044: "b0b0b0ff",
    # The black bar at the bottom of short menus: View 0x0dad1474's second imag element (0x1c97, 240 wide,
    # no bitmap source) is tinted with COLR 0x28 (black). Same colour as the menu background instead.
    0x0DAD0028: "242424ff",
    # The same bar in non-menu views (re-tinted to 0x30 in dark_mode_toggle.py): invisible in Dark Mode.
    # Cover Flow's flip-side track list (Views 0x14cd / 0x14ce): the tint (COLR 0x43, white, used only there)
    # of the row-background image element 0x1e05/0x1e0b, which shows on every other row. The panel
    # behind the rows is #242424 (dark_mode_toggle.py, LISTBG); these rows are a lighter grey.
    0x0DAD0043: "3a3a3aff",
    # Notes instructions page background (its first element, tinted 0x2b = white and unused elsewhere):
    0x0DAD002B: "242424ff",
    # Notes instructions page: its grey body text (0x78, 474747, only used there)
    0x0DAD0078: "d0d0d0ff",
    # Secondary grey text (artist names under song titles in Views 0x0dad1499..14a6, 12 refs): 6d6d6d -> light grey
    0x0DAD0025: "c8c8c8ff",

    # Not mapped, although black: 0x28 is only ever the tint of the drop-shadow image (bitmap
    # 0x0dad01a4, a black alpha gradient) under menus; turned white it drew a white line.
    # 0x3f is Cover Flow's title/artist text (View 0x0dad14cc), drawn over the OpenGL renderer's
    # white background, which Dark Mode can't change yet; light text there was unreadable.
    # Also not mapped: 0x57 is the Now Playing screen's black backdrop (an image tint in
    # Views 0x0dad1512/1515) and 0x58 is text on its dark overlays (Views 0x0dad151c/151e). Now
    # Playing is dark in the stock OS and must look the same with Dark Mode on.

    # No white -> dark entries: every white COLR that views reference is a *text* colour or an
    # image tint (0x12 = highlighted menu text; 0x18, 0x74, 0x84, 0x89, 0xa1 = white text on
    # screens that are already dark), not a surface. Menu backgrounds come from the table
    # element's built-in white default instead (see dark_mode_toggle.py).
}


def rgba(hex_str: str) -> bytes:
    return bytes.fromhex(hex_str)


def build_patches(body: bytes) -> list[Patch]:
    db = ResourceDB(body)
    patches = []

    # Palette inversion map:
    # Key = COLR resource ID, Value = new RGBA hex string
    #
    # Core system colors:
    # 0xdad0013: Primary black text (000000ff) -> pure white (ffffffff)
    # 0xdad0012: White backgrounds/tints (ffffffff) -> dark surface (1e1e1eff)
    # 0xdad0018: Full-screen view backgrounds (ffffffff) -> deep black (121212ff)
    # 0xdad0074: Menu & window background panels (ffffffff) -> dark surface (1c1c1eff)
    # 0xdad0084: View backgrounds (ffffffff) -> dark surface (1c1c1eff)
    # 0xdad004e: Near-black text (111111ff) -> near-white text (e5e5e5ff)
    # 0xdad0028: Black text/elements (000000ff) -> white (ffffffff)
    # 0xdad0087: Black UI icons/text (000000ff) -> white (ffffffff)
    # 0xdad0088: Black UI icons/text (000000ff) -> white (ffffffff)
    # 0xdad0037: Black text (000000ff) -> white (ffffffff)
    # 0xdad0055: Black text (000000ff) -> white (ffffffff)
    # 0xdad0057: Black text (000000ff) -> white (ffffffff)
    # 0xdad0058: Black text (000000ff) -> white (ffffffff)
    # 0xdad0070: Black text (000000ff) -> white (ffffffff)
    # 0xdad0076: Black text (000000ff) -> white (ffffffff)
    # 0xdad0086: Black text (000000ff) -> white (ffffffff)

    for cid, new_hex in COLOR_MAP.items():
        res = db.get("COLR", cid)
        if res is not None:
            old_data = res.data(body)
            new_data = rgba(new_hex)
            patches.append(Patch(res.offset, old_data, new_data))

    return patches


def main() -> int:
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <retailos.dec> <output.dfu>", file=sys.stderr)
        return 1

    src, dst = sys.argv[1], sys.argv[2]
    img = Img1.parse(Path(src).read_bytes())

    # Build on top of the working combined camera build or base firmware
    patches = build_patches(img.body)
    body = apply(img.body, patches)

    out = Img1.make_unsigned(body, entrypoint=img.header.entrypoint)
    Path(dst).write_bytes(out.to_bytes())
    print(f"Wrote {dst} with {len(patches)} inverted theme color patches.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
