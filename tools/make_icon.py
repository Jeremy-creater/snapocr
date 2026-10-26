"""Build the application icon from the source artwork (M2 WI-18, PRD F5-6, plan D8). Dev script.

Run from the repository root with the project venv active:

    python tools/make_icon.py

Writes ``src/snapocr/gui/assets/snapocr.ico`` (16/24/32/48/256, PNG entries)
and ``snapocr-256.png``. Both are committed; rerun only if the artwork or the
constants below change.

The artwork's blue rounded square sits in a soft, jagged glow. Instead of
keying out colours, the alpha channel is replaced by a geometric,
antialiased rounded-rect mask measured on the 1254 px source: glow, shadow
and background go in one step and no light fringe is left. The RGB comes from
the source unchanged.
"""

from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets" / "Blue OCR Scanner App Icon.png"
OUT_DIR = ROOT / "src" / "snapocr" / "gui" / "assets"

# Measured on the 1254x1254 source (alpha >= 128 on the centre lines): the
# square's edges are x 157..1096 and y 170..1092. A mask inset by 2 px with a
# 300 px corner radius touches no pixel whose source alpha is below 200; 280 px
# or a smaller inset still picks up glow at the corners.
SQUARE = (157.0, 170.0, 1096.0, 1092.0)  # left, top, right, bottom edges
INSET = 2.0
RADIUS = 300.0
# A 960 px square canvas centred on the shape (about 1 % margin per side).
CANVAS = (146, 151, 960)  # x, y, side
SIZES = (16, 24, 32, 48, 256)

_ICONDIR = struct.Struct("<HHH")
_ENTRY = struct.Struct("<BBBBHHII")


def build_ico(entries: list[tuple[int, bytes]]) -> bytes:
    """An ICO file holding one PNG image per ``(size, png_bytes)``, in the given order."""
    if not entries:
        raise ValueError("an icon needs at least one image")
    for size, png in entries:
        if not 1 <= size <= 256 or not png:
            raise ValueError(f"bad icon entry: size {size}, {len(png)} bytes")
    header = _ICONDIR.pack(0, 1, len(entries))
    offset = _ICONDIR.size + _ENTRY.size * len(entries)
    table, blobs = [], []
    for size, png in entries:
        side = size % 256  # 256 is stored as 0
        table.append(_ENTRY.pack(side, side, 0, 0, 1, 32, len(png), offset))
        blobs.append(png)
        offset += len(png)
    return header + b"".join(table) + b"".join(blobs)


def parse_ico(data: bytes) -> list[tuple[int, bytes]]:
    """The ``(size, image_bytes)`` entries of an ICO file (the inverse of ``build_ico``)."""
    if len(data) < _ICONDIR.size:
        raise ValueError("too short for an ICO header")
    reserved, kind, count = _ICONDIR.unpack_from(data, 0)
    if reserved != 0 or kind != 1 or count == 0:
        raise ValueError("not an ICO file")
    if len(data) < _ICONDIR.size + _ENTRY.size * count:
        raise ValueError("ICO directory is truncated")
    entries = []
    for i in range(count):
        w, _h, _colors, _res, _planes, _bpp, length, offset = _ENTRY.unpack_from(data, _ICONDIR.size + _ENTRY.size * i)
        if offset + length > len(data):
            raise ValueError(f"ICO entry {i} points past the end of the file")
        entries.append((w or 256, data[offset : offset + length]))
    return entries


def rounded_rect_alpha(size: tuple[int, int], rect: tuple[float, float, float, float], radius: float):
    """An antialiased Alpha8 mask: 255 inside the rounded rect ``(x, y, w, h)``, 0 outside."""
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath

    mask = QImage(size[0], size[1], QImage.Format.Format_Alpha8)
    mask.fill(0)
    path = QPainterPath()
    path.addRoundedRect(QRectF(*rect), radius, radius)
    painter = QPainter(mask)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.fillPath(path, QColor(0, 0, 0, 255))
    painter.end()
    return mask


def masked_artwork(source):
    """The source with its alpha replaced by the measured mask, cropped to the square canvas."""
    from PySide6.QtGui import QImage

    left, top, right, bottom = SQUARE
    rect = (left + INSET, top + INSET, right - left - 2 * INSET, bottom - top - 2 * INSET)
    mask = rounded_rect_alpha((source.width(), source.height()), rect, RADIUS)
    # Drop the source alpha first (about 252 inside the square): setAlphaChannel
    # multiplies with the existing alpha, and the mask alone must decide it.
    image = source.convertToFormat(QImage.Format.Format_RGB32).convertToFormat(QImage.Format.Format_ARGB32)
    image.setAlphaChannel(mask)
    x, y, side = CANVAS
    return image.copy(x, y, side, side)


def render_sizes(artwork) -> dict[int, object]:
    """Smoothly scaled, premultiplied while scaling so edges blend with transparency, not black."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage

    premultiplied = artwork.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    out = {}
    for size in SIZES:
        scaled = premultiplied.scaled(size, size, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        out[size] = scaled.convertToFormat(QImage.Format.Format_ARGB32)
    return out


def _png(image) -> bytes:
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice

    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, "PNG"):
        raise RuntimeError("PNG encoding failed")
    return bytes(data)


def main() -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication, QImage

    app = QGuiApplication(sys.argv[:1])  # noqa: F841 - QImage scaling needs a GUI application
    source = QImage(str(SOURCE))
    if source.isNull():
        print(f"cannot read {SOURCE}", file=sys.stderr)
        return 1
    images = render_sizes(masked_artwork(source))
    pngs = {size: _png(image) for size, image in images.items()}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "snapocr.ico").write_bytes(build_ico([(s, pngs[s]) for s in SIZES]))
    (OUT_DIR / "snapocr-256.png").write_bytes(pngs[256])
    print(f"wrote {OUT_DIR / 'snapocr.ico'} and snapocr-256.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
