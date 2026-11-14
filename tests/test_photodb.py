import struct
from pathlib import Path

from nanocam import photodb


def _db(entries):
    # minimal database: one mhni record per entry (format, offset, size)
    out = b""
    for fmt, off, size in entries:
        rec = b"mhni" + struct.pack("<II", 0x4c, 0x4c) + bytes(4) + struct.pack("<III", fmt, off, size)
        out += rec + bytes(0x4c - len(rec))
    return out


def test_compact_packs_and_rewrites_offsets(tmp_path: Path):
    (tmp_path / "Thumbs").mkdir()
    data = bytearray(3 * 1000)
    blobs = [b"\xff\xd8A\xff\xd9", b"\xff\xd8BB\xff\xd9", b"\xff\xd8CCC\xff\xd9"]
    for i, b in enumerate(blobs):
        data[i * 1000:i * 1000 + len(b)] = b
    (tmp_path / "Thumbs" / "F1081_1.ithmb").write_bytes(data)
    (tmp_path / "Photo Database").write_bytes(_db([(1081, i * 1000, len(b)) for i, b in enumerate(blobs)]
                                                    + [(1087, 0x48000, 294912)]))
    old, new = photodb.compact(tmp_path, 1081, align=16)
    assert (old, new) == (3000, 48)
    refs = photodb.image_refs((tmp_path / "Photo Database").read_bytes())
    packed = (tmp_path / "Thumbs" / "F1081_1.ithmb").read_bytes()
    for r, b in zip([r for r in refs if r.fmt == 1081], blobs):
        assert packed[r.offset:r.offset + r.size] == b
    assert [r.offset for r in refs if r.fmt == 1087] == [0x48000]
