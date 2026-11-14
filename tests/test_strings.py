from nanocam.strings import find_strings, grep_strings

DATA = b"\x00\x01Video Camera\x00\xffabc\x00CameraShutter\x00"


def test_finds_strings_with_offsets():
    assert list(find_strings(DATA)) == [(2, "Video Camera"), (20, "CameraShutter")]


def test_skips_short_runs():
    assert "abc" not in [text for _, text in find_strings(DATA)]


def test_grep_is_case_insensitive():
    assert [text for _, text in grep_strings(DATA, "shutter")] == ["CameraShutter"]
