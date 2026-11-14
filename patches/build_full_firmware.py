"""Build the complete iPod nano 5G custom firmware:
- Photo Camera mode (still capture + Photos slot writer, 200 slots)
- Dark Mode toggle in Settings > General (replaces Rotate; switches the palette at run time)

Usage:
    .\\.venv\\Scripts\\python.exe patches/build_full_firmware.py firmware/n5g-retailos.dec firmware/n5g-full-build.dfu [slots] [next_number]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from nanocam.img1 import Img1  # noqa: E402
from nanocam.patch import apply  # noqa: E402
import dark_mode_toggle as dm  # noqa: E402
import photo_mode as pm  # noqa: E402
import photos_slot as ps  # noqa: E402


def build_all_patches(body: bytes, slots: int = 200, offset: int = 0):
    camera_patches = pm.build_all(body)
    slot_patches = ps.slot_patches(body, slots, offset)
    # slot_patches already cuts the Voice Memos entry, whose code space both use
    dark_mode_patches = dm.build_patches(body, cut_voice_memos=False)
    return camera_patches + slot_patches + dark_mode_patches


def main() -> int:
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <retailos.dec> <output.dfu> [slots=200] [next_pic_number=0]", file=sys.stderr)
        return 1

    src, dst = sys.argv[1], sys.argv[2]
    slots = int(sys.argv[3]) if len(sys.argv) > 3 else 200
    next_number = int(sys.argv[4]) if len(sys.argv) > 4 else 0
    offset = ps.default_offset(slots, next_number)

    img = Img1.parse(Path(src).read_bytes())
    patches = build_all_patches(img.body, slots, offset)
    body = apply(img.body, patches)

    print(f"Applied {len(patches)} total patches:")
    print(f"  - Photo Camera & Still Capture: {len(pm.build_all(img.body))} patches")
    print(f"  - Photos Slot Writer ({slots} slots): {len(ps.slot_patches(img.body, slots, offset))} patches")
    print(f"  - Dark Mode Settings Toggle: {len(dm.build_patches(img.body, cut_voice_memos=False))} patches")

    out = Img1.make_unsigned(body, entrypoint=img.header.entrypoint)
    Path(dst).write_bytes(out.to_bytes())
    print(f"Wrote {dst} successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
