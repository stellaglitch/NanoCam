"""FIRST PHOTO PATCH: the camera's center button takes a photo instead of recording.

Calls Apple's own, unused TakePhoto(pipeline, path, callback) at 0x0809c3e6
(see docs/firmware-notes.md section 14). The camera pipeline then tags the next
frame for JPEG, attaches the path, and the JPEG stages write "<path>.jpg".

This first version is deliberately simple:
  - it applies in BOTH Video Camera and Photo Camera (recording is disabled)
  - every press writes the same file, /DCIM/000APPLE/IMG_9000.jpg

Includes patches/photo_camera_menu.py so the Photo Camera item is also there.

Usage:
    python patches/take_photo.py firmware/n5g-retailos.dec firmware/n5g-take-photo.dfu
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from nanocam import thumb  # noqa: E402
from nanocam.img1 import Img1  # noqa: E402
from nanocam.patch import Patch, apply  # noqa: E402
from photo_camera_menu import build_patches as menu_patches  # noqa: E402

BASE = 0x07FD1D84            # main OS: address = body offset + BASE

TAKE_PHOTO = 0x0809C3E6      # Apple's TakePhoto(pipeline, path, cb[3])
PIPELINE_GLOBAL = 0x086BA368  # holds the Pipeline* once the camera has started
HOOK = 0x080C8602            # camera dispatcher: center-button branch (posts command 8)
RETURN_TRUE = 0x080C866E     # "movs r0,#1; pop {...,pc}": event handled
CAVE = 0x08276B10            # 244 bytes of unused padding at 0x08276b0c..0x08276c00
PHOTO_PATH = b"/DCIM/000APPLE/IMG_9000\0"  # encoder appends ".jpg"

# The original instructions at HOOK that we overwrite (6 bytes):
#   add r5,#0xff ; add r5,#5 ; ldrb r0,[r5,#1]
HOOK_ORIGINAL = bytes.fromhex("ff35 0535 6878".replace(" ", ""))


def build_stub() -> bytes:
    """Thumb code placed in the cave:

        push {r4, lr}
        ldr  r0, =PIPELINE_GLOBAL
        ldr  r0, [r0]           ; r0 = pipeline (NULL if the camera isn't running)
        cmp  r0, #0
        beq  done
        adr  r1, path
        adr  r2, no_callback
        bl   TakePhoto
    done:
        pop  {r4, pc}
        (literal, no_callback = 12 zero bytes, path)
    """
    a = CAVE
    lit = CAVE + 20          # data starts on a 4-byte boundary after 10 halfwords
    no_cb = lit + 4
    path = no_cb + 12
    done = CAVE + 18

    code = b""
    code += thumb.push_r4_lr()
    code += thumb.ldr_pc(a + len(code), 0, lit)
    code += thumb.ldr_reg0(0, 0)
    code += thumb.cmp_imm(0, 0)
    code += thumb.beq(a + len(code), done)
    code += thumb.adr(a + len(code), 1, path)
    code += thumb.adr(a + len(code), 2, no_cb)
    code += thumb.bl(a + len(code), TAKE_PHOTO)
    assert a + len(code) == done
    code += thumb.pop_r4_pc()
    assert a + len(code) == lit
    code += struct.pack("<I", PIPELINE_GLOBAL)
    code += bytes(12)
    code += PHOTO_PATH
    return code


def photo_patches(body: bytes) -> list[Patch]:
    stub = build_stub()
    if body[CAVE - BASE:CAVE - BASE + len(stub)] != bytes(len(stub)):
        raise ValueError("code cave isn't empty; wrong firmware?")
    # At the hook: call the stub, then report the button as handled.
    hook = thumb.bl(HOOK, CAVE) + thumb.b(HOOK + 4, RETURN_TRUE)
    return [
        Patch(CAVE - BASE, bytes(len(stub)), stub),
        Patch(HOOK - BASE, HOOK_ORIGINAL, hook),
    ]


def main() -> int:
    src, dst = sys.argv[1], sys.argv[2]
    img = Img1.parse(Path(src).read_bytes())
    patches = menu_patches(img.body) + photo_patches(img.body)
    body = apply(img.body, patches)
    for p in patches:
        print(f"{p.offset:#09x}  {p.old.hex()} -> {p.new.hex()}")
    Path(dst).write_bytes(Img1.make_unsigned(body, entrypoint=img.header.entrypoint).to_bytes())
    print(f"wrote {dst} ({len(patches)} patches)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
