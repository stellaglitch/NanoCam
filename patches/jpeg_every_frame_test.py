"""EXPERIMENT: send every camera frame down the JPEG branch, to prove it can write files.

Frames carry flag bits at frame+0x48. Flag 0x20 means "make a JPEG", but we
haven't found what sets it. Every viewfinder frame has flag 0x1, so this makes
the JPEG path's checks test 0x1 instead of 0x20:

  - splitter (FUN_08113810): push the frame onto the JPEG queue
  - JPEG preprocess (FUN_080edd8c): accept the frame, and convert it to an
    encodable image
  - JPEG encode (FUN_080ea028): encode it and write the .jpg

If .jpg files appear, the JPEG stages run and the only missing piece is the
per-press trigger. If nothing appears, the JPEG stages aren't started in this mode.

Expect it to be slow, and possibly to stall or fill the disk. Open the camera
for a few seconds only. A normal reboot returns to stock firmware.

(An earlier version patched the capture thread's 7/0xd constants. Those turned
out to be buffer limits, not flags, so it tested nothing.)

Includes patches/photo_camera_menu.py so the Photo Camera item is also there.

Stage 3 (all four checks) crashed: a white screen, then a reboot, on opening
Photo Camera. A stage number enables only the first checks, to find which part
crashes:
  1 = splitter only (frames reach preprocess and are released)
  2 = + preprocess accept/convert (frames reach the encoder, not encoded)
  3 = everything

Usage:
    python patches/jpeg_every_frame_test.py firmware/n5g-retailos.dec firmware/n5g-jpeg-stage1.dfu 1
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from nanocam.img1 import Img1  # noqa: E402
from nanocam.patch import Patch, apply  # noqa: E402
from photo_camera_menu import build_patches as menu_patches  # noqa: E402

BASE = 0x07FD1D84  # main OS: address = body offset + BASE

MOVS_R1_0X20 = bytes([0x20, 0x21])  # Thumb "movs r1, #0x20"
MOVS_R1_0X01 = bytes([0x01, 0x21])  # Thumb "movs r1, #0x1"

# Address of each "movs r1,#0x20" that feeds a flag test on the JPEG path.
JPEG_CHECKS = {
    "splitter: push to JPEG queue": 0x08113972,
    "preprocess: accept frame": 0x080EDDB8,
    "preprocess: convert to encodable image": 0x080EDDD8,
    "encode: write .jpg": 0x080EA03E,
}


# How many of JPEG_CHECKS (in order) each stage enables.
STAGE_CHECKS = {1: 1, 2: 3, 3: 4}


def flag_patches(stage: int = 3) -> list[Patch]:
    addrs = list(JPEG_CHECKS.values())[:STAGE_CHECKS[stage]]
    return [Patch(addr - BASE, MOVS_R1_0X20, MOVS_R1_0X01) for addr in addrs]


def main() -> int:
    src, dst = sys.argv[1], sys.argv[2]
    stage = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    img = Img1.parse(Path(src).read_bytes())
    patches = menu_patches(img.body) + flag_patches(stage)
    print(f"stage {stage}: {', '.join(list(JPEG_CHECKS)[:STAGE_CHECKS[stage]])}")
    body = apply(img.body, patches)
    for p in patches:
        print(f"{p.offset:#09x}  {p.old.hex()} -> {p.new.hex()}")
    Path(dst).write_bytes(Img1.make_unsigned(body, entrypoint=img.header.entrypoint).to_bytes())
    print(f"wrote {dst} ({len(patches)} patches)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
