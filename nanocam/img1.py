"""Read and build IMG1 ("8900") firmware containers.

Every executable image the nano 5G boots (WTF, RetailOS, ...) is wrapped in an
IMG1 container: a fixed-size header, then the body, then a signature and
certificate chain. Format docs: https://freemyipod.org/wiki/IMG1

Python concepts used here:
- `struct` turns raw bytes into numbers and back, like a C struct.
- `@dataclass` generates __init__/__repr__/__eq__ for a plain data class.
- `classmethod` gives an alternate constructor (`Img1.parse(data)`).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from .devices import NANO5G_IMG1_HEADER_SIZE, NANO5G_SOC_CODE

# Format codes stored in the header.
FORMAT_SIGNED_ENCRYPTED = 1
FORMAT_SIGNED = 2
FORMAT_X509_SIGNED_ENCRYPTED = 3
FORMAT_X509_SIGNED = 4  # Not encrypted. Haxed DFU doesn't check the signature, so we use this.

FORMAT_NAMES = {
    FORMAT_SIGNED_ENCRYPTED: "signed+encrypted",
    FORMAT_SIGNED: "signed",
    FORMAT_X509_SIGNED_ENCRYPTED: "x509 signed+encrypted",
    FORMAT_X509_SIGNED: "x509 signed (plaintext)",
}

# "<" = little-endian, "4s" = 4 raw bytes, "B" = uint8, "I" = uint32, "H" = uint16.
HEADER_STRUCT = struct.Struct("<4s3sBIIIII32sHH16s")

SIGNATURE_LENGTH = 0x80
CERT_LENGTH = 0x300


class Img1Error(ValueError):
    """Raised when bytes don't look like a nano 5G IMG1 image."""


@dataclass
class Img1Header:
    magic: bytes
    version: bytes
    format: int
    entrypoint: int
    body_length: int
    data_length: int
    footer_cert_offset: int
    footer_cert_length: int
    salt: bytes = bytes(32)
    unknown1: int = 0
    security_epoch: int = 0
    header_signature: bytes = bytes(16)

    def pack(self) -> bytes:
        return HEADER_STRUCT.pack(
            self.magic, self.version, self.format, self.entrypoint,
            self.body_length, self.data_length,
            self.footer_cert_offset, self.footer_cert_length,
            self.salt, self.unknown1, self.security_epoch, self.header_signature,
        )

    @classmethod
    def unpack(cls, data: bytes) -> Img1Header:
        # `*` spreads the tuple from struct into the dataclass's positional arguments.
        return cls(*HEADER_STRUCT.unpack_from(data))

    @property
    def format_name(self) -> str:
        return FORMAT_NAMES.get(self.format, f"unknown ({self.format})")

    @property
    def is_encrypted(self) -> bool:
        return self.format in (FORMAT_SIGNED_ENCRYPTED, FORMAT_X509_SIGNED_ENCRYPTED)


@dataclass
class Img1:
    header: Img1Header
    body: bytes

    @classmethod
    def parse(cls, data: bytes) -> Img1:
        if len(data) < NANO5G_IMG1_HEADER_SIZE:
            raise Img1Error(f"file is only {len(data)} bytes, too small for an IMG1 header")

        header = Img1Header.unpack(data)
        if header.magic != NANO5G_SOC_CODE:
            raise Img1Error(f"magic is {header.magic!r}, expected {NANO5G_SOC_CODE!r} (nano 5G)")
        if header.version != b"2.0":
            raise Img1Error(f"unsupported IMG1 version {header.version!r}")

        start = NANO5G_IMG1_HEADER_SIZE
        end = start + header.body_length
        if end > len(data):
            raise Img1Error(f"body claims {header.body_length:#x} bytes but file is truncated")

        return cls(header=header, body=data[start:end])

    @classmethod
    def make_unsigned(cls, body: bytes, entrypoint: int = 0) -> Img1:
        """Wrap a flat ARM binary so haxed DFU will accept and run it."""
        # The body must be a multiple of 16 bytes. -len % 16 is the padding needed.
        body = body + bytes(-len(body) % 16)
        header = Img1Header(
            magic=NANO5G_SOC_CODE,
            version=b"2.0",
            format=FORMAT_X509_SIGNED,
            entrypoint=entrypoint,
            body_length=len(body),
            data_length=len(body) + SIGNATURE_LENGTH + CERT_LENGTH,
            footer_cert_offset=len(body) + SIGNATURE_LENGTH,
            footer_cert_length=CERT_LENGTH,
        )
        return cls(header=header, body=body)

    def to_bytes(self) -> bytes:
        """Serialize, with dummy signature and certificate bytes the haxed bootrom ignores."""
        packed = self.header.pack()
        padding = bytes(NANO5G_IMG1_HEADER_SIZE - len(packed))
        return packed + padding + self.body + b"S" * SIGNATURE_LENGTH + b"C" * CERT_LENGTH
