"""Find readable text inside a firmware image, like the Unix `strings` tool.

Strings are the quickest way into an unknown binary: class names, log messages
and UI labels tell you which part of the code does what.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

# A run of printable ASCII bytes (space through ~). `{n,}` means "n or more".
_PRINTABLE = rb"[\x20-\x7e]"


def find_strings(data: bytes, min_length: int = 5) -> Iterator[tuple[int, str]]:
    """Yield (offset, text) for each printable ASCII run of at least min_length bytes."""
    # A generator (`yield`) produces results one at a time instead of building a big list.
    for match in re.finditer(_PRINTABLE + b"{%d,}" % min_length, data):
        yield match.start(), match.group().decode("ascii")


def grep_strings(data: bytes, pattern: str, min_length: int = 5) -> Iterator[tuple[int, str]]:
    """Like find_strings, but only strings matching a case-insensitive regex."""
    regex = re.compile(pattern, re.IGNORECASE)
    return ((offset, text) for offset, text in find_strings(data, min_length) if regex.search(text))
