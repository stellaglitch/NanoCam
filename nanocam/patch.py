"""Patch bytes inside a decrypted firmware body.

Every patch says what bytes it expects to find before it writes. That catches
the most common mistake, patching the wrong offset or the wrong firmware version,
before a broken image ever reaches the iPod.
"""

from __future__ import annotations

from dataclasses import dataclass


class PatchError(ValueError):
    """Raised when a patch doesn't match the firmware it's applied to."""


@dataclass(frozen=True)  # frozen: a Patch can't be changed after it's made.
class Patch:
    offset: int  # body offset, as printed by `nanocam strings`
    old: bytes
    new: bytes

    def __post_init__(self) -> None:
        if len(self.old) != len(self.new):
            raise PatchError(f"patch at {self.offset:#x} changes length; that would shift everything after it")


def apply(body: bytes, patches: list[Patch]) -> bytes:
    """Return a copy of body with every patch applied."""
    out = bytearray(body)  # bytes can't be modified in place, bytearray can
    for p in patches:
        found = bytes(out[p.offset:p.offset + len(p.old)])
        if found != p.old:
            raise PatchError(f"at {p.offset:#x} expected {p.old!r}, found {found!r}")
        out[p.offset:p.offset + len(p.new)] = p.new
    return bytes(out)


def string_patch_at(body: bytes, offset: int, old: str, new: str) -> Patch:
    """A patch that replaces the one copy of `old` at `offset` with `new` (NUL-padded)."""
    if len(new) > len(old):
        raise PatchError(f"{new!r} is longer than {old!r}; there's no room for it in place")
    old_b = old.encode("ascii") + b"\0"
    return Patch(offset, old_b, new.encode("ascii").ljust(len(old_b), b"\0"))


def string_patches(body: bytes, old: str, new: str) -> list[Patch]:
    """Patches that replace every complete NUL-terminated copy of `old` with `new`.

    `new` may be shorter than `old`; it's padded with NULs to keep the same size.
    """
    if len(new) > len(old):
        raise PatchError(f"{new!r} is longer than {old!r}; there's no room for it in place")
    old_b = old.encode("ascii") + b"\0"
    new_b = new.encode("ascii").ljust(len(old_b), b"\0")

    patches = []
    start = body.find(old_b)
    while start != -1:
        # Skip matches that are the end of a longer string, like "MyVideo Camera".
        if start == 0 or not 0x20 <= body[start - 1] <= 0x7E:
            patches.append(Patch(start, old_b, new_b))
        start = body.find(old_b, start + 1)
    if not patches:
        raise PatchError(f"{old!r} not found")
    return patches
