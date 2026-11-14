"""Photo firmware + Camera Roll photo-open test, with the DCIM purge's file deletion disabled.

The camera-start scan (FUN_0809b27c) deletes IMG_NNNN.* for every item it puts
on its purge list, and so far every photo item has ended up there
(docs/firmware-notes.md sections 23–23f). This build:
  - photo_mode.py: numbered PIC_NNNN.jpg photos, shutter sound, Video Camera untouched
  - camera_roll_photos_test.py: selecting a photo item in Camera Roll posts
    EnterPhotosScreen (opens the camera photo viewer)
  - 0x0809b684: `bl 0x0827a610` (delete file) -> `movs r0,#0; nop`. The purge loop
    still runs and logs, but no file is removed. (Directories are still handled by
    the other branch, FUN_08234698, which isn't touched.)
  - 0x0809b67e: the purge's other branch, `bl 0x08234698`, -> `movs r0,#0; nop` (v3).
  - 0x0812d50e: RemoveItem's `bl 0x0809da18` (delete an item's .DAT + media) -> `movs r0,#0; nop`.

Usage:
    python patches/no_purge.py firmware/n5g-retailos.dec firmware/n5g-no-purge-test.dfu
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from nanocam import thumb as t  # noqa: E402
from nanocam.img1 import Img1  # noqa: E402
from nanocam.patch import Patch, apply  # noqa: E402
from camera_roll_photos_test import roll_patches  # noqa: E402
from photo_mode import BASE, build_all  # noqa: E402

PURGE_DELETE_CALL = 0x0809B684
REMOVE_ITEM_DELETE_CALL = 0x0812D50E   # in the DB's RemoveItem (FUN_0812d454): bl FUN_0809da18 (deletes .DAT + media)
DELETE_ITEM_FILES = 0x0809DA18
PURGE_OTHER_CALL = 0x0809B67E          # the purge's other branch: bl FUN_08234698 (also deletes; flag meaning unsure)
REMOVE_ENTRY = 0x08234698
DELETE_FILE = 0x0827A610
NOP = bytes.fromhex("c046")      # mov r8, r8


PURGE_LOOP_TEST = 0x0809B788    # beq 0x0809b78c (exit purge loop) / else b 0x0809b5c0 (next id)
PURGE_LOOP_EXIT = 0x0809B78C
SCAN_NEW_ITEM_EXIT = 0x0809B4E4   # b 0x0809b53a: after adding a new item -> cleanup, return 10
SCAN_RETURN_10 = 0x0809B53A
SCAN_NEXT_ENTRY = 0x0809B56E      # next directory entry


def no_purge_patches() -> list[Patch]:
    return [
        # v4: skip the purge loop entirely. v1-v3 NOP'd its delete calls, but the loop
        # re-opens the folder listing after every deletion, so with nothing deleted it
        # found the same file forever, leaking 0x44 bytes per pass -> crash on eject (v3).
        Patch(PURGE_LOOP_TEST - BASE, t.bcond("eq", PURGE_LOOP_TEST, PURGE_LOOP_EXIT),
              t.b(PURGE_LOOP_TEST, PURGE_LOOP_EXIT)),
        # RemoveItem(id, delete_files) -> FUN_0809da18 deletes an item's .DAT + media.
        # Also stops Camera Roll's own Delete from removing files (test only).
        Patch(REMOVE_ITEM_DELETE_CALL - BASE, t.bl(REMOVE_ITEM_DELETE_CALL, DELETE_ITEM_FILES),
              t.movs_imm(0, 0) + NOP),
        # v5: after a new item is imported and added, keep scanning instead of returning 10
        # (which the mount treats as failure). Tests the "return 10 rolls new items back" idea.
        Patch(SCAN_NEW_ITEM_EXIT - BASE, t.b(SCAN_NEW_ITEM_EXIT, SCAN_RETURN_10),
              t.b(SCAN_NEW_ITEM_EXIT, SCAN_NEXT_ENTRY)),
    ]


def main() -> int:
    src, dst = sys.argv[1], sys.argv[2]
    img = Img1.parse(Path(src).read_bytes())
    patches = build_all(img.body) + roll_patches() + no_purge_patches()
    body = apply(img.body, patches)
    for p in patches[-4:]:
        print(f"{p.offset:#09x}  {p.old.hex()} -> {p.new.hex()}")
    Path(dst).write_bytes(Img1.make_unsigned(body, entrypoint=img.header.entrypoint).to_bytes())
    print(f"wrote {dst} ({len(patches)} patches)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
