"""Synthetic QImages for offscreen GUI tests (M2 WI-13 onwards)."""

from __future__ import annotations

from PySide6.QtGui import QColor, QImage


def gradient(w: int, h: int) -> QImage:
    """An opaque RGB32 image whose every pixel differs from its neighbours."""
    image = QImage(w, h, QImage.Format.Format_RGB32)
    for y in range(h):
        for x in range(w):
            image.setPixelColor(x, y, QColor((x * 7 + y) % 256, (y * 11 + x * 3) % 256, (x + y) * 5 % 256))
    return image


def pixels(image: QImage) -> list[list[int]]:
    """Rows of 0xAARRGGBB values, after converting to RGB32."""
    rgb = image.convertToFormat(QImage.Format.Format_RGB32)
    return [[rgb.pixel(x, y) for x in range(rgb.width())] for y in range(rgb.height())]
