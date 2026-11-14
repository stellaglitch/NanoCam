"""EXPERIMENT: open camera photos from Camera Roll.

Camera Roll's select handler (FUN_080847d4) casts the chosen item:
  type 2 UnSyncedPhotoListProps  -> FUN_081d1294, then FUN_0809c95c(this, 0)
  type 6 UnSyncedAllContentProps -> FUN_081d1188, then FUN_0809c95c(this, 0)
FUN_0809c95c sets up the Photos model's album but never shows a screen. Its
dormant twin FUN_0809c8c0(this, flag) does the same and then posts
"EnterPhotosScreen", which Camera Roll's SEVT maps to PushScreen
PhotosGL_Camera_Screen. This patch makes the shared call at 0x08084858 go to
FUN_0809c8c0 instead. See docs/firmware-notes.md section 22.

Usage:
    python patches/camera_roll_photos_test.py firmware/n5g-retailos.dec firmware/n5g-camera-roll-photos-test.dfu
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

SELECT_CALL = 0x08084858      # bl 0x0809c95c  (shared by photo-list and all-content items)
SET_ALBUM = 0x0809C95C        # sets the album, shows nothing
SET_ALBUM_AND_SHOW = 0x0809C8C0  # same, then posts EnterPhotosScreen (dormant)


def roll_patches() -> list[Patch]:
    return [Patch(SELECT_CALL - BASE, t.bl(SELECT_CALL, SET_ALBUM), t.bl(SELECT_CALL, SET_ALBUM_AND_SHOW))]


def main() -> int:
    src, dst = sys.argv[1], sys.argv[2]
    img = Img1.parse(Path(src).read_bytes())
    patches = build_all(img.body) + roll_patches()
    body = apply(img.body, patches)
    p = patches[-1]
    print(f"{p.offset:#09x}  {p.old.hex()} -> {p.new.hex()}")
    Path(dst).write_bytes(Img1.make_unsigned(body, entrypoint=img.header.entrypoint).to_bytes())
    print(f"wrote {dst} ({len(patches)} patches)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
