"""EXPERIMENT: identify the camera's timer element by re-binding it to fixed text.

The camera screen's VCvs 0x0dad1648 binds text element 0x0dad1c88 (main View
0x0dad1470) to the live data source SORC 0x1a8 (kind 0xa480). This test binds it to
SORC 0x399 instead, the "Video Camera" label. If those words appear where the timer
was, that element is the timer. Both camera modes are affected. Built on
photos_slot.py (200 slots, PIC_0000 -> slot 0) with the "Camera" labels.

Usage:
    python patches/timer_binding_test.py firmware/n5g-retailos.dec firmware/n5g-timer-binding-test.dfu
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

CAMERA_VCVS = 0x0DAD1648
BINDING_AT = 0x18          # {0x10, element 0x0dad1c88, 1, 4, 'SORC', sorc}: sorc is at +0x18
LIVE_SOURCE = 0x1A8
TEST_SOURCE = 0x399        # SORC -> Str 0x0dad0946 "Video Camera"


def binding_patch(body: bytes, new_source: int) -> Patch:
    r = ResourceDB(body).get("VCvs", CAMERA_VCVS)
    d = r.data(body)
    if struct.unpack_from("<I", d, 8)[0] != 0x0DAD1C88 or struct.unpack_from("<I", d, BINDING_AT)[0] != LIVE_SOURCE:
        raise ValueError("unexpected VCvs layout")
    return Patch(r.offset + BINDING_AT, struct.pack("<I", LIVE_SOURCE), struct.pack("<I", new_source))


def main() -> int:
    src, dst = sys.argv[1], sys.argv[2]
    img = Img1.parse(Path(src).read_bytes())
    patches = pm.build_all(img.body) + ps.slot_patches(img.body, 200, 0) + [binding_patch(img.body, TEST_SOURCE)]
    body = apply(img.body, patches)
    p = patches[-1]
    print(f"{p.offset:#09x}  {p.old.hex()} -> {p.new.hex()}")
    Path(dst).write_bytes(Img1.make_unsigned(body, entrypoint=img.header.entrypoint).to_bytes())
    print(f"wrote {dst} ({len(patches)} patches)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
