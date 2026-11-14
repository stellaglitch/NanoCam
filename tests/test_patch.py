import pytest

from nanocam.patch import Patch, PatchError, apply, string_patch_at, string_patches

BODY = b"\x00Video Camera\x00MyVideo Camera\x00Video Camera\x00"


def test_replaces_whole_strings_only():
    patches = string_patches(BODY, "Video Camera", "Photo Camera")
    assert [p.offset for p in patches] == [1, 29]
    assert apply(BODY, patches) == b"\x00Photo Camera\x00MyVideo Camera\x00Photo Camera\x00"


def test_patch_at_one_offset_only():
    out = apply(BODY, [string_patch_at(BODY, 29, "Video Camera", "Video Cam 3")])
    assert out == b"\x00Video Camera\x00MyVideo Camera\x00Video Cam 3\x00\x00"


def test_patch_at_wrong_offset_is_rejected():
    with pytest.raises(PatchError, match="expected"):
        apply(BODY, [string_patch_at(BODY, 14, "Video Camera", "Video Cam 3")])


def test_shorter_replacement_is_nul_padded():
    out = apply(BODY, string_patches(BODY, "Video Camera", "Photos"))
    assert out[1:14] == b"Photos" + b"\x00" * 7
    assert len(out) == len(BODY)


def test_longer_replacement_is_rejected():
    with pytest.raises(PatchError, match="longer"):
        string_patches(BODY, "Video Camera", "Photo Camera Mode")


def test_wrong_bytes_are_rejected():
    with pytest.raises(PatchError, match="expected"):
        apply(BODY, [Patch(0, b"XY", b"AB")])


def test_length_changing_patch_is_rejected():
    with pytest.raises(PatchError, match="length"):
        Patch(0, b"ab", b"abc")
