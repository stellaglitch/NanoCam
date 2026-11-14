import pytest

from nanocam.devices import NANO5G_IMG1_HEADER_SIZE
from nanocam.img1 import FORMAT_X509_SIGNED, HEADER_STRUCT, Img1, Img1Error


def test_header_is_80_bytes():
    assert HEADER_STRUCT.size == 80


def test_wrap_then_parse_round_trips():
    payload = b"\xfe\xff\xff\xea"  # ARM instruction `b .` (loop forever)
    raw = Img1.make_unsigned(payload, entrypoint=0x10).to_bytes()

    img = Img1.parse(raw)
    assert img.header.format == FORMAT_X509_SIGNED
    assert img.header.entrypoint == 0x10
    assert img.body[:4] == payload
    assert len(img.body) == 16  # padded up to a multiple of 16
    assert raw[NANO5G_IMG1_HEADER_SIZE:NANO5G_IMG1_HEADER_SIZE + 4] == payload


def test_rejects_other_devices():
    raw = bytearray(Img1.make_unsigned(b"x").to_bytes())
    raw[0:4] = b"8720"  # nano 4G magic
    with pytest.raises(Img1Error, match="nano 5G"):
        Img1.parse(bytes(raw))


def test_rejects_truncated_file():
    with pytest.raises(Img1Error, match="too small"):
        Img1.parse(b"8730")
