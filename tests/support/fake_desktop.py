"""Fake desktop boundaries for the controller (M2 WI-17): capture provider and notifier.

The hotkey backend fake is ``support.fake_hotkeys.FakeHotkeyTable``. These
fakes return scripted values; tests assert on clipboard, windows and the
notices shown, not on how often something was called.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter

from snapocr.actions.outcomes import Notice
from snapocr.geometry import Point, Rect, ScreenInfo
from snapocr.gui.boundaries import Capture, CaptureError


def desktop_image(w: int, h: int) -> QImage:
    """A fast, non-uniform opaque image (two crossing gradients)."""
    image = QImage(w, h, QImage.Format.Format_RGB32)
    image.fill(QColor(40, 40, 40))
    painter = QPainter(image)
    for start, end, a, b in (
        (QPointF(0, 0), QPointF(w, 0), QColor(255, 0, 0, 160), QColor(0, 0, 255, 160)),
        (QPointF(0, 0), QPointF(0, h), QColor(0, 255, 0, 120), QColor(255, 255, 0, 120)),
    ):
        gradient = QLinearGradient(start, end)
        gradient.setColorAt(0, a)
        gradient.setColorAt(1, b)
        painter.fillRect(0, 0, w, h, gradient)
    painter.end()
    return image


@dataclass
class FakeCapture:
    image: QImage
    origin: Point
    screens: tuple[ScreenInfo, ...]
    work_areas: dict[str, Rect] = field(default_factory=dict)
    error: str | None = None
    taken: list[Capture] = field(default_factory=list)

    def capture(self) -> Capture:
        if self.error is not None:
            raise CaptureError(self.error)
        cap = Capture(self.image, self.origin, self.screens, dict(self.work_areas))
        self.taken.append(cap)
        return cap


@dataclass
class RecordingNotifier:
    notices: list[Notice] = field(default_factory=list)

    def notify(self, notice: Notice) -> None:
        self.notices.append(notice)
