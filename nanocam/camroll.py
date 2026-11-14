"""Camera Roll .DAT files ("CamFiPod"), as written by the firmware (FUN_08235210).

Layout (all little-endian):
  0x00  8s   magic b"doPIFmaC" ("CamFiPod" stored byte-reversed per 4 bytes)
  0x08  u16 1, u16 1
  0x0c  u16 header size (0x1c), u16 info size (0x24), u16 thumb entry size (8), u16 thumb count (3)
  0x14  u32 info offset (0x1c), u32 thumb table offset
  0x1c  info: 16s file name ("IMG_0006.mp4"), u32 kind (1001 for every video seen),
        u32 duration (probably ms), u32 0, u16 content width, u16 content height, u8 1, 3 pad
  0x40  thumbnails, RGB565 little-endian
  end   thumb table: count x {u32 artwork format id, u32 offset}

Thumbnails seen in every video DAT:
  0x437  80x80    square centre crop
  0x42a  64x64    square centre crop
  0x43f  384x384  the frame fitted inside (288x384 portrait), letterboxed in black
"""

from __future__ import annotations

import struct
from pathlib import Path

MAGIC = b"doPIFmaC"
KIND_PHOTO = 501           # FUN_0825a314: JPG/JPEG -> 501, MP4 -> 1001, MOV -> 1002
KIND_VIDEO = 1001
THUMBS = [(0x437, 80), (0x42A, 64), (0x43F, 384)]


def rgb565(im) -> bytes:
    out = bytearray()
    for r, g, b in im.convert("RGB").getdata():
        out += struct.pack("<H", ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3))
    return bytes(out)


def parse(data: bytes) -> dict:
    if data[:8] != MAGIC:
        raise ValueError("not a CamFiPod .DAT")
    _, _, hsize, isize, esize, count, ioff, toff = struct.unpack_from("<HHHHHHII", data, 8)
    name = data[ioff:ioff + 16].split(b"\0")[0].decode()
    kind, duration, zero, w, h, flag = struct.unpack_from("<IIIHHB", data, ioff + 16)
    thumbs = [struct.unpack_from("<II", data, toff + i * esize) for i in range(count)]
    return dict(name=name, kind=kind, duration=duration, width=w, height=h, flag=flag, thumbs=thumbs)


def build(name: str, jpeg: Path, kind: int = KIND_PHOTO, duration: int = 0) -> bytes:
    from PIL import Image, ImageOps

    im = ImageOps.exif_transpose(Image.open(jpeg)).convert("RGB")
    blobs = []
    for fmt, size in THUMBS:
        if size == 384:
            fit = ImageOps.contain(im, (size, size))
            canvas = Image.new("RGB", (size, size))
            canvas.paste(fit, ((size - fit.width) // 2, (size - fit.height) // 2))
            content = fit.size
            blobs.append((fmt, rgb565(canvas)))
        else:
            blobs.append((fmt, rgb565(ImageOps.fit(im, (size, size)))))

    info = name.encode().ljust(16, b"\0")[:16]
    info += struct.pack("<IIIHHB3x", kind, duration, 0, content[0], content[1], 1)
    body = b""
    table = b""
    off = 0x1C + len(info)
    for fmt, blob in blobs:
        table += struct.pack("<II", fmt, off + len(body))
        body += blob
    toff = 0x1C + len(info) + len(body)
    header = MAGIC + struct.pack("<HHHHHHII", 1, 1, 0x1C, len(info), 8, len(blobs), 0x1C, toff)
    return header + info + body + table
