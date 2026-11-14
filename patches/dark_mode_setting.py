"""Replace "Rotate" in Settings > General with "Dark Mode".

Since "Rotate" is ALREADY a working on/off toggle setting in RetailOS:
- The cell structure (CLov) already has the 3 SORCs (label, hilite label, toggle state).
- The stylesheet (TVCS) already defines the toggle row styles.
- The event handler (ToggleSetting_Rotate) and event script (SEVT) are already 100% matched and working.
- No cell IDs, table counts, or event scripts need to change.

We only do two clean string patches:
1. Re-purpose spare string Str 0x0dad0da9 "World Wide (TEST)" -> "Dark Mode".
2. Repoint Rotate's SORC 0x985 and SORC 0x986 (label and highlighted label) to Str 0x0dad0da9.

Usage:
    .\\.venv\\Scripts\\python.exe patches/dark_mode_setting.py firmware/n5g-retailos.dec firmware/n5g-dark-mode-test.dfu
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nanocam.img1 import Img1
from nanocam.patch import Patch, apply, string_patch_at
from nanocam.resources import ResourceDB

STR_SPARE = 0x0DAD0DA9  # "World Wide (TEST)"
SPARE_TEXT = "World Wide (TEST)"
NEW_LABEL = "Dark Mode"
STR_VALUE_ON = 0x0DAD0E32  # "Cover Flow": the Rotate row's value when on (off is "Off")

# Rotate toggle label sources in Settings > General (Cell 0x0dad11b5)
SORC_ROTATE_LABEL = 0x985
SORC_ROTATE_HILITE = 0x986


def u32_patch(body: bytes, offset: int, new: int) -> Patch:
    return Patch(offset, body[offset:offset + 4], struct.pack("<I", new))


def build_patches(body: bytes) -> list[Patch]:
    db = ResourceDB(body)
    patches = []

    # 1. Rename spare string to "Dark Mode"
    spare_str = db.get("Str ", STR_SPARE)
    if spare_str is None:
        raise ValueError("Spare string not found")
    patches.append(string_patch_at(body, spare_str.offset, SPARE_TEXT, NEW_LABEL))

    # 2. Point Rotate's label SORCs at "Dark Mode"
    sorc_label = db.get("SORC", SORC_ROTATE_LABEL)
    sorc_hilite = db.get("SORC", SORC_ROTATE_HILITE)
    if sorc_label is None or sorc_hilite is None:
        raise ValueError("Rotate label SORCs not found")

    # Verify existing kind is 0x80 (string source)
    kind_label = struct.unpack_from("<I", body, sorc_label.offset + 12)[0]
    kind_hilite = struct.unpack_from("<I", body, sorc_hilite.offset + 12)[0]
    if kind_label != 0x80 or kind_hilite != 0x80:
        raise ValueError(f"Expected kind 0x80, got {kind_label:#x}, {kind_hilite:#x}")

    patches.append(u32_patch(body, sorc_label.offset + 16, STR_SPARE))
    patches.append(u32_patch(body, sorc_hilite.offset + 16, STR_SPARE))

    # 3. The row's On value: Rotate showed "Cover Flow" (Str 0x0dad0e32, used only by this row)
    value_on = db.get("Str ", STR_VALUE_ON)
    patches.append(string_patch_at(body, value_on.offset, "Cover Flow", "On"))

    return patches


def main() -> int:
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <retailos.dec> <output.dfu>", file=sys.stderr)
        return 1

    src = Path(sys.argv[1]).read_bytes()
    img = Img1.parse(src)

    patches = build_patches(img.body)
    body = apply(img.body, patches)

    for p in patches:
        print(f"0x{p.offset:07x}  {p.old.hex()} -> {p.new.hex()}")

    out = Img1.make_unsigned(body, entrypoint=img.header.entrypoint)
    Path(sys.argv[2]).write_bytes(out.to_bytes())
    print(f"wrote {sys.argv[2]} ({len(patches)} patches)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
