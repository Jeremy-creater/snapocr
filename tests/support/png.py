"""Independent, spec-based PNG builders for tests (stdlib only: zlib + struct)."""

from __future__ import annotations

import struct
import zlib

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def chunk(kind: bytes, payload: bytes) -> bytes:
    crc = zlib.crc32(kind + payload) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", crc)


def ihdr_payload(w: int, h: int) -> bytes:
    # bit depth 8, colour type 2 (RGB), compression 0, filter 0, interlace 0
    return struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)


def make_png_header(w: int, h: int) -> bytes:
    """Signature + complete IHDR chunk (exactly 33 bytes)."""
    return PNG_SIGNATURE + chunk(b"IHDR", ihdr_payload(w, h))


def make_png(w: int, h: int) -> bytes:
    """A complete, decodable RGB PNG of the given size (all black)."""
    raw = b"".join(b"\x00" + b"\x00\x00\x00" * w for _ in range(h))
    return (
        make_png_header(w, h)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def set_ihdr_size(data: bytes, w: int, h: int) -> bytes:
    """Rewrite the IHDR width/height of ``data`` and recompute the IHDR CRC."""
    payload = struct.pack(">II", w, h) + data[24:29]
    return data[:8] + chunk(b"IHDR", payload) + data[33:]
