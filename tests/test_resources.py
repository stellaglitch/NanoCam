import struct

import pytest

from nanocam.resources import ResourceDB, cevt_handlers, fourcc


def make_db() -> bytes:
    """A tiny resource database with two types, laid out like the firmware's."""
    index = 0x10
    types = [(b"View", [(0x0DAD0001, b"\x01\x02\x03\x04")]), (b"Str ", [(7, b"hi\x00\x00"), (8, b"yo\x00\x00")])]

    data = b""
    entries = b""
    type_table = b""
    entries_start = 12 + len(types) * 16
    for name, items in types:
        type_table += struct.pack("<4I", struct.unpack(">I", name)[0], len(items), 1, entries_start + len(entries))
        for rid, blob in items:
            entries += struct.pack("<3I", rid, len(data), len(blob))
            data += blob
    data_base = entries_start + len(entries)
    header = struct.pack("<3I", 3, data_base, len(types))
    return bytes(index) + header + type_table + entries + data


def test_lists_types_and_ids():
    db = ResourceDB(make_db(), index_offset=0x10)
    assert list(db.by_type) == ["View", "Str "]
    assert [r.id for r in db.by_type["Str "]] == [7, 8]


def test_reads_resource_data():
    body = make_db()
    db = ResourceDB(body, index_offset=0x10)
    assert db.get("Str ", 8).data(body) == b"yo\x00\x00"
    assert db.get("View", 0x0DAD0001).data(body) == b"\x01\x02\x03\x04"
    assert db.get("View", 99) is None


def test_containing_finds_owner():
    body = make_db()
    db = ResourceDB(body, index_offset=0x10)
    r = db.get("Str ", 7)
    assert db.containing(r.offset + 1) == r


def test_cevt_handlers_parse_events_and_actions():
    # Two entries: event 10 -> handler 20; event 11 -> handler 0x4a with one action (op 5, args [6, 7]).
    data = struct.pack("<H", 2)
    data += struct.pack("<HBHH", 10, 0x31, 20, 0)
    data += struct.pack("<HBHH", 11, 0x31, 0x4A, 1) + struct.pack("<4H", 5, 2, 6, 7)
    assert cevt_handlers(data) == {10: (20, 5), 11: (0x4A, 12)}


def test_cevt_handlers_reject_unknown_layout():
    with pytest.raises(ValueError, match="format not understood"):
        cevt_handlers(struct.pack("<HHB", 1, 10, 0x31) + b"\x00" * 9)


def test_fourcc_reads_big_endian_code():
    assert fourcc(0x4954454D) == "ITEM"
