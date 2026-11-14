"""Read the UI resource database inside RetailOS.

The iPod's UI (menus, screens, strings, transitions) is data, stored as typed
resources much like classic Mac OS resource files. Layout, from the firmware's
own lookup code (FUN_081ff738 / FUN_081ff80a):

    index header   u32 ?, u32 data_base_offset, u32 type_count
    type table     type_count x { u32 type (four-char code), u32 count, u32 ?, u32 entries_offset }
    entries        count x { u32 id, u32 data_offset, u32 size }

entries_offset is relative to the index; data_offset is relative to
index + data_base_offset. Four-char codes are stored little-endian, so the
bytes of 'ITEM' read "METI" in a hex dump.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

# Body offset of the index in the nano 5G RetailOS we've been working with.
NANO5G_INDEX_OFFSET = 0x58200C


def fourcc(code: int) -> str:
    return struct.pack(">I", code).decode("latin1")


@dataclass(frozen=True)
class Resource:
    type: str
    id: int
    offset: int  # body offset of the resource's data
    size: int

    def data(self, body: bytes) -> bytes:
        return body[self.offset:self.offset + self.size]


class ResourceDB:
    def __init__(self, body: bytes, index_offset: int = NANO5G_INDEX_OFFSET):
        self.body = body
        _, data_base, type_count = struct.unpack_from("<3I", body, index_offset)
        self.data_base = index_offset + data_base

        self.by_type: dict[str, list[Resource]] = {}
        for i in range(type_count):
            code, count, _, entries = struct.unpack_from("<4I", body, index_offset + 12 + i * 16)
            name = fourcc(code)
            self.by_type[name] = [
                Resource(name, rid, self.data_base + off, size)
                for rid, off, size in struct.iter_unpack("<3I", body[index_offset + entries:][:count * 12])
            ]

    def get(self, type: str, id: int) -> Resource | None:
        return next((r for r in self.by_type.get(type, []) if r.id == id), None)

    def all(self) -> list[Resource]:
        return [r for rs in self.by_type.values() for r in rs]

    def containing(self, offset: int) -> Resource | None:
        """The resource whose data covers a body offset, if any."""
        return next((r for r in self.all() if r.offset <= offset < r.offset + r.size), None)

    def text(self, type: str, id: int) -> str | None:
        """A NUL-terminated string resource (`Str ` for UI text, `StrT` for symbol names)."""
        r = self.get(type, id)
        return r.data(self.body).split(b"\0")[0].decode("latin1") if r else None

    def symbol_id(self, name: str) -> int:
        """Look up a symbol (a `StrT` resource) by name, e.g. "HandleCameraSelected"."""
        for r in self.by_type["StrT"]:
            if r.data(self.body).split(b"\0")[0] == name.encode():
                return r.id
        raise KeyError(name)


def cevt_handlers(data: bytes) -> dict[int, tuple[int, int]]:
    """Map each event symbol in a CEVT script to (handler symbol, byte offset of the handler).

    Format (all little-endian, symbols are StrT IDs):
        u16 count
        count x { u16 event, u8 op (0x31), u16 handler, u16 nargs,
                  nargs x { u16 action, u16 n, n x u16 arg } }
    A handler is either a C++ "Handle..." name or 0x4a, which runs the listed
    actions instead (e.g. navigator.PushScreen(screen)).
    """
    def u16(o: int) -> int:
        return struct.unpack_from("<H", data, o)[0]

    handlers: dict[int, tuple[int, int]] = {}
    o = 2
    for _ in range(u16(0)):
        event, handler, nargs = u16(o), u16(o + 3), u16(o + 5)
        handlers[event] = (handler, o + 3)
        o += 7
        for _ in range(nargs):
            o += 4 + 2 * u16(o + 2)
    if o != len(data):
        raise ValueError(f"CEVT parse used {o} of {len(data)} bytes; format not understood")
    return handlers
