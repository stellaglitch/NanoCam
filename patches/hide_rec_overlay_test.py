"""EXPERIMENT: hide the camera's recording overlay (record dot + timer) to identify it.

The camera screen (SUse 0x0dad0618) uses View 0x0dad14bd: an overlay with three
elements, imag 0x0dad1dbf, imag 0x0dad1dc0 and text 0x0dad1dc1 (Helvetica). Each
element's tag is followed by a word 0x00010000 that looks like a flags field. This
test image clears those three words in BOTH camera modes; if the dot and timer
vanish, the final build will toggle them per mode instead.

Built on photos_slot.py (200 slots, PIC_0000 -> slot 0).

Usage:
    python patches/hide_rec_overlay_test.py firmware/n5g-retailos.dec firmware/n5g-hide-overlay-test.dfu
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

# v1 tried View 0x0dad14bd (imag, imag, text): no change on the device.
# v2: the camera's main View 0x0dad1470. Its text element 0x0dad1c88 is the one whose
# data source the camera's VCvs 0x0dad1648 overrides (SORC 0x1a8), so it's the timer;
# imag 0x0dad1c87 just before it is probably the record dot.
OVERLAY_VIEW = 0x0DAD1470
FLAG_WORDS = (0x230, 0x2B4)            # word after each element tag (imag 1c87, text 1c88)
TAGS = {0x22C: b"imag", 0x2B0: b"text"}


def overlay_patches(body: bytes) -> list[Patch]:
    view = ResourceDB(body).get("View", OVERLAY_VIEW)
    data = view.data(body)
    for off, tag in TAGS.items():
        if data[off:off + 4][::-1] != tag:
            raise ValueError(f"View {OVERLAY_VIEW:#x}: expected {tag!r} at {off:#x}")
    out = []
    for w in FLAG_WORDS:
        cur = struct.unpack_from("<I", data, w)[0]          # 0x00010000 (imag) / 0x00010100 (text)
        out.append(Patch(view.offset + w, struct.pack("<I", cur), struct.pack("<I", cur & ~0x00010000)))
    return out


def main() -> int:
    src, dst = sys.argv[1], sys.argv[2]
    img = Img1.parse(Path(src).read_bytes())
    patches = pm.build_all(img.body) + ps.slot_patches(img.body, 200, 0) + overlay_patches(img.body)
    body = apply(img.body, patches)
    for p in patches[-len(FLAG_WORDS):]:
        print(f"{p.offset:#09x}  {p.old.hex()} -> {p.new.hex()}")
    Path(dst).write_bytes(Img1.make_unsigned(body, entrypoint=img.header.entrypoint).to_bytes())
    print(f"wrote {dst} ({len(patches)} patches)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
