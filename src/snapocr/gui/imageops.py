"""QImage crop, PNG encode / decode and thumbnails (F6-2, F7-1, F10-1)."""

from __future__ import annotations

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRect, Qt
from PySide6.QtGui import QImage

from snapocr.geometry import Rect, fit_size


def crop(image: QImage, box: Rect) -> QImage:
    """The pixels of ``box`` (image coordinates) as a detached copy; ``box`` must lie inside."""
    inside = 0 <= box.x and 0 <= box.y and box.x + box.w <= image.width() and box.y + box.h <= image.height()
    if box.w < 1 or box.h < 1 or not inside:
        raise ValueError(f"crop box {box} is not inside the {image.width()}x{image.height()} image")
    return image.copy(QRect(box.x, box.y, box.w, box.h))


def encode_png(image: QImage) -> bytes:
    if image.isNull():
        raise ValueError("cannot encode an empty image")
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, "PNG"):
        raise ValueError("PNG encoding failed")
    buffer.close()
    return bytes(data)


def decode_png(png: bytes) -> QImage:
    image = QImage.fromData(png, "PNG")
    if image.isNull():
        raise ValueError("data is not a readable PNG image")
    return image


def thumbnail(image: QImage, max_box: tuple[int, int]) -> QImage:
    """``image`` scaled to ``fit_size`` (smooth); a copy when it already fits."""
    w, h = fit_size((image.width(), image.height()), max_box)
    if (w, h) == (image.width(), image.height()):
        return image.copy()
    return image.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
