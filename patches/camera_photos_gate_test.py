"""EXPERIMENT: switch on the Photos app's built-in camera-photo browser.

See docs/firmware-notes.md section 20. On top of photo_mode.py (numbered photos +
shutter sound), this:
  1. FUN_0821aebc "camera photo count":   movs r0,#0 -> movs r0,#1
  2. FUN_08232e52 "camera photos on":     movs r0,#0 -> movs r0,#1
  3. FUN_080d3140 album row builder: the `beq` at 0x080d3194 that skips
     "assert(!camera photos on)" becomes an unconditional `b`.
  4. Main menu PhotosSelected (0x080dd210): always post "PhotosSelected" instead
     of "EmptyPhotosSelected" (v1 without this showed "No photos", no change).

Expected outcomes: Photos stops saying "No photos" and shows some row; choosing
it may open PhotosGL_Camera_Screen. A crash just reboots.

Usage:
    python patches/camera_photos_gate_test.py firmware/n5g-retailos.dec firmware/n5g-camera-photos-test.dfu
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from nanocam import thumb as t  # noqa: E402
from nanocam.img1 import Img1  # noqa: E402
from nanocam.patch import Patch, apply  # noqa: E402
from photo_mode import BASE, build_all  # noqa: E402

CAMERA_PHOTO_COUNT = 0x0821AEBC
CAMERA_PHOTOS_ON = 0x08232E52
ASSERT_SKIP = 0x080D3194       # beq 0x080d319e
ASSERT_DONE = 0x080D319E
MENU_PHOTOS_CHECK = 0x080DD230  # main menu PhotosSelected: bne -> "PhotosSelected", else "EmptyPhotosSelected"
MENU_PHOTOS_YES = 0x080DD236


def gate_patches() -> list[Patch]:
    return [
        Patch(CAMERA_PHOTO_COUNT - BASE, t.movs_imm(0, 0), t.movs_imm(0, 1)),
        Patch(CAMERA_PHOTOS_ON - BASE, t.movs_imm(0, 0), t.movs_imm(0, 1)),
        Patch(ASSERT_SKIP - BASE, t.bcond("eq", ASSERT_SKIP, ASSERT_DONE), t.b(ASSERT_SKIP, ASSERT_DONE)),
        # v2: the main menu decides "No photos" before the Photos app runs; always enter it.
        Patch(MENU_PHOTOS_CHECK - BASE, t.bcond("ne", MENU_PHOTOS_CHECK, MENU_PHOTOS_YES),
              t.b(MENU_PHOTOS_CHECK, MENU_PHOTOS_YES)),
    ]


def main() -> int:
    src, dst = sys.argv[1], sys.argv[2]
    img = Img1.parse(Path(src).read_bytes())
    patches = build_all(img.body) + gate_patches()
    body = apply(img.body, patches)
    for p in patches[-4:]:
        print(f"{p.offset:#09x}  {p.old.hex()} -> {p.new.hex()}")
    Path(dst).write_bytes(Img1.make_unsigned(body, entrypoint=img.header.entrypoint).to_bytes())
    print(f"wrote {dst} ({len(patches)} patches)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
