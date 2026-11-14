"""Minimal reader/editor for the iPod Photos library (`<iPod>/Photos/Photo Database`).

The database is a tree of records, each starting with a 4-byte tag and
{u32 header length, u32 total length}. Image entries (`mhni`) say where each
pre-rendered picture lives:  +16 u32 format id, +20 u32 offset, +24 u32 size
in `Thumbs/F<format>_1.ithmb`.

`compact()` packs one format's pictures tightly (iTunes reserves a fixed slot per
picture, which is mostly padding for small JPEGs) and rewrites the offsets.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ImageRef:
    pos: int        # position of the mhni record in the database
    fmt: int
    offset: int
    size: int


def image_refs(db: bytes) -> list[ImageRef]:
    refs = []
    o = 0
    while o < len(db) - 12:
        tag = db[o:o + 4]
        if not tag.isalpha():
            o += 4
            continue
        hl = struct.unpack_from("<I", db, o + 4)[0]
        if tag == b"mhni":
            fmt, off, size = struct.unpack_from("<III", db, o + 16)
            refs.append(ImageRef(o, fmt, off, size))
        o += hl if hl else 4
    return refs


def compact(photos_dir: Path, fmt: int, align: int = 512) -> tuple[int, int]:
    """Pack format `fmt` tightly. Returns (old file size, new file size)."""
    db_path = photos_dir / "Photo Database"
    ithmb = photos_dir / "Thumbs" / f"F{fmt}_1.ithmb"
    db = bytearray(db_path.read_bytes())
    data = ithmb.read_bytes()
    refs = [r for r in image_refs(bytes(db)) if r.fmt == fmt]
    out = bytearray()
    for r in sorted(refs, key=lambda r: r.offset):
        blob = data[r.offset:r.offset + r.size]
        if len(blob) != r.size:
            raise ValueError(f"entry at {r.pos:#x} runs past the end of {ithmb.name}")
        new_off = len(out)
        out += blob
        out += bytes((-len(out)) % align)
        struct.pack_into("<I", db, r.pos + 20, new_off)
    ithmb.write_bytes(out)
    db_path.write_bytes(db)
    return len(data), len(out)
