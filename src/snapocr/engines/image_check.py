"""Structural PNG validation of input bytes, before any decoding.

Stdlib only; never decodes pixel data. Error messages never contain input bytes.
"""

from __future__ import annotations

import struct

from snapocr.engines.errors import InvalidImageError, InvalidImageReason

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
# signature (8) + IHDR length (4) + type (4) + payload (13) + CRC (4)
_IHDR_END = 33


def check_png_bytes(data: object) -> tuple[int, int]:
    """Return ``(width, height)`` from the IHDR chunk, or raise ``InvalidImageError``.

    Only ``bytes`` / ``bytearray`` are accepted, so a ``str`` can never be
    mistaken for a file path or URL further down the pipeline.
    """
    if not isinstance(data, (bytes, bytearray)):
        raise InvalidImageError(InvalidImageReason.NOT_BYTES, f"got {type(data).__name__}")
    if not data:
        raise InvalidImageError(InvalidImageReason.EMPTY)
    if data[:8] != PNG_SIGNATURE:
        raise InvalidImageError(InvalidImageReason.NOT_PNG, "missing PNG signature")
    if len(data) < _IHDR_END:
        raise InvalidImageError(
            InvalidImageReason.TRUNCATED, f"{len(data)} bytes, IHDR needs {_IHDR_END}"
        )
    if data[12:16] != b"IHDR":
        raise InvalidImageError(InvalidImageReason.NOT_PNG, "first chunk is not IHDR")
    width, height = struct.unpack(">II", data[16:24])
    if width == 0 or height == 0:
        raise InvalidImageError(
            InvalidImageReason.NOT_PNG, f"invalid IHDR dimensions {width}x{height}"
        )
    return width, height
