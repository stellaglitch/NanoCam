"""EXPERIMENT: hide the camera's record badge (red dot + "0:00:00", top right) by
pointing its three elements' colours at a fully transparent colour.

View 0x0dad14bd is the badge: imag 0x0dad1dbf (COLR 0x0dad0012, white = tint),
imag 0x0dad1dc0 (COLR 0x0dad0028, black) and text 0x0dad1dc1 (COLR 0x0dad0013).
COLR resources are RGBA; 0x0dad001a is 00000000 (transparent). Both camera modes
are affected in this test. Built on photos_slot.py (200 slots) with the "Camera" labels.

Usage:
    python patches/hide_badge_test.py firmware/n5g-retailos.dec firmware/n5g-hide-badge-test.dfu
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from nanocam.img1 import Img1  # noqa: E402
from nanocam.patch import Patch, apply  # noqa: E402
from nanocam.resources import ResourceDB  # noqa: E402
import photo_mode as pm  # noqa: E402
import photos_slot as ps  # noqa: E402

BADGE_VIEW = 0x0DAD14BD
COLOUR_REFS = {0x05C: 0x0DAD0012, 0x0E0: 0x0DAD0028, 0x168: 0x0DAD0013}   # offset in View -> COLR
TRANSPARENT = 0x0DAD001A


def badge_patches(body: bytes, colour: int = TRANSPARENT) -> list[Patch]:
    db = ResourceDB(body)
    if db.get("COLR", TRANSPARENT).data(body) != bytes(4):
        raise ValueError("COLR 0x0dad001a isn't transparent")
    view = db.get("View", BADGE_VIEW)
    d = view.data(body)
    out = []
    for off, old in COLOUR_REFS.items():
        if struct.unpack_from("<I", d, off)[0] != old:
            raise ValueError(f"View {BADGE_VIEW:#x}+{off:#x} isn't COLR {old:#x}")
        out.append(Patch(view.offset + off, struct.pack("<I", old), struct.pack("<I", colour)))
    return out


def main() -> int:
    src, dst = sys.argv[1], sys.argv[2]
    img = Img1.parse(Path(src).read_bytes())
    patches = pm.build_all(img.body) + ps.slot_patches(img.body, 200, 0) + badge_patches(img.body)
    body = apply(img.body, patches)
    for p in patches[-3:]:
        print(f"{p.offset:#09x}  {p.old.hex()} -> {p.new.hex()}")
    Path(dst).write_bytes(Img1.make_unsigned(body, entrypoint=img.header.entrypoint).to_bytes())
    print(f"wrote {dst} ({len(patches)} patches)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
