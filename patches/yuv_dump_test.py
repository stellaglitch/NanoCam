"""EXPERIMENT: photo firmware (photo_mode.py, PIC_ names) with the encoder's debug
raw-frame dump switched on, so each photo also writes PIC_NNNN.yuv next to the JPEG.

The JPEG encoder FUN_080f533c calls FUN_08106838(path, raw, width, height) when the
byte at 0x08550950 is non-zero. That routine byte-swaps each 16-bit pair of the frame
and writes width*height*2 bytes to <path with .jpg -> .yuv>. Used to learn the raw
frame layout for the Photos-slot writer (docs/firmware-notes.md section 28).

Usage:
    python patches/yuv_dump_test.py firmware/n5g-retailos.dec firmware/n5g-yuv-dump-test.dfu
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from nanocam.img1 import Img1  # noqa: E402
from nanocam.patch import Patch, apply  # noqa: E402
from photo_mode import BASE, build_all  # noqa: E402

DUMP_FLAG = 0x08550950
DUMP_SKIP = 0x080F55D0          # beq 0x080f55de: skip the dump when the flag is 0
NOP = bytes.fromhex("c046")


def main() -> int:
    src, dst = sys.argv[1], sys.argv[2]
    img = Img1.parse(Path(src).read_bytes())
    # v1 set the flag byte, but no .yuv appeared (the byte seems to be cleared at boot),
    # so v3 removes the check instead. (v2's build missed this change: it was v1 again.)
    from nanocam import thumb as t
    patches = build_all(img.body) + [
        Patch(DUMP_SKIP - BASE, t.bcond("eq", DUMP_SKIP, 0x080F55DE), NOP),
    ]
    body = apply(img.body, patches)
    Path(dst).write_bytes(Img1.make_unsigned(body, entrypoint=img.header.entrypoint).to_bytes())
    print(f"wrote {dst} ({len(patches)} patches)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
