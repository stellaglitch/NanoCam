"""Turn the main menu's "Composers" item into a second camera entry called "Photo Camera".

Composers is off in the main menu by default and still reachable under Music,
so nothing is lost. Enable it in Settings > Main Menu to see the new item.

All edits are in place (no resources added):
1. The unused string "Test Menu Item (has no ID)" becomes "Photo Camera".
2. The Composers cell's two label sources (SORC) point at that string.
3. In the main menu's event script, the Composers cell's chosen/linger
   handlers become HandleCameraSelected / HandleCameraHilited.

Usage:
    python patches/photo_camera_menu.py firmware/n5g-retailos.dec firmware/n5g-photocam-menu.dfu
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

# Lets this script import nanocam when run from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nanocam.img1 import Img1  # noqa: E402
from nanocam.patch import Patch, apply, string_patch_at  # noqa: E402
from nanocam.resources import ResourceDB, cevt_handlers  # noqa: E402

MAIN_MENU_SCREEN = 0x0DAD0868   # owns the main menu's CEVT event script
COMPOSERS_CELL = 0x0DAD114C     # main menu cell #9 (TVCL 0xd)
SPARE_STRING = "Test Menu Item (has no ID)"
NEW_LABEL = "Camera"
# The main menu's split-screen preview for the camera item(s) shows this copy of
# "Video Camera" (Str 0x0dad0bff via SORC 0x322 in preview View 0x0dad14e8).
PREVIEW_STRING_ID = 0x0DAD0BFF
PREVIEW_OLD = "Video Camera"
PREVIEW_NEW = "Camera"


def u32_patch(body: bytes, offset: int, new: int) -> Patch:
    return Patch(offset, body[offset:offset + 4], struct.pack("<I", new))


def u16_patch(body: bytes, offset: int, new: int) -> Patch:
    return Patch(offset, body[offset:offset + 2], struct.pack("<H", new))


def build_patches(body: bytes) -> list[Patch]:
    db = ResourceDB(body)
    patches = []

    # 1. Reuse the spare test string for the new label.
    spare = next(r for r in db.by_type["Str "] if db.text("Str ", r.id) == SPARE_STRING)
    patches.append(string_patch_at(body, spare.offset, SPARE_STRING, NEW_LABEL))

    # 1b. Rename the home screen's camera preview text.
    preview = db.get("Str ", PREVIEW_STRING_ID)
    if db.text("Str ", PREVIEW_STRING_ID) != PREVIEW_OLD:
        raise ValueError(f"Str {PREVIEW_STRING_ID:#x} isn't {PREVIEW_OLD!r}")
    patches.append(string_patch_at(body, preview.offset, PREVIEW_OLD, PREVIEW_NEW))

    # 2. Point the Composers cell's label sources at it.
    #    CLov: u32 n, then n x { 0x10, property, 1, 4, 'SORC', sorc_id }
    cell = db.get("CLov", COMPOSERS_CELL).data(body)
    for k in range(struct.unpack_from("<I", cell, 0)[0]):
        sorc_id = struct.unpack_from("<I", cell, 4 + k * 24 + 20)[0]
        sorc = db.get("SORC", sorc_id)
        # SORC: { 1, 0xc, 'SORC', kind, value, 1 }; kind 0x80 = value is a Str ID.
        kind = struct.unpack_from("<I", body, sorc.offset + 12)[0]
        if kind != 0x80:
            raise ValueError(f"SORC {sorc_id:#x} isn't a string source (kind {kind:#x})")
        patches.append(u32_patch(body, sorc.offset + 16, spare.id))

    # 3. Send the cell's events to the camera handlers.
    cevt = db.get("CEVT", MAIN_MENU_SCREEN)
    handlers = cevt_handlers(cevt.data(body))
    cid = COMPOSERS_CELL  # events are named after the cell ID in decimal
    for event, old_name, new_name in [
        (f"table.cid.{cid}.chosen", "HandleComposersSelected", "HandleCameraSelected"),
        (f"table.cid.{cid}.linger", "HandleComposersHilited", "HandleCameraHilited"),
    ]:
        handler, offset = handlers[db.symbol_id(event)]
        if handler != db.symbol_id(old_name):
            raise ValueError(f"{event} is handled by {db.text('StrT', handler)}, expected {old_name}")
        patches.append(u16_patch(body, cevt.offset + offset, db.symbol_id(new_name)))

    return patches


def main() -> int:
    src, dst = sys.argv[1], sys.argv[2]
    img = Img1.parse(Path(src).read_bytes())
    patches = build_patches(img.body)
    body = apply(img.body, patches)
    for p in patches:
        print(f"{p.offset:#09x}  {p.old.hex()} -> {p.new.hex()}")
    Path(dst).write_bytes(Img1.make_unsigned(body, entrypoint=img.header.entrypoint).to_bytes())
    print(f"wrote {dst} ({len(patches)} patches)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
