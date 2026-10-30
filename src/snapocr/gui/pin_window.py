"""A screenshot pinned on the screen (PRD F15; M4 plan D14).

A frameless, always-on-top tool window that shows one image scaled to the
window. Its size is kept in logical pixels, so it looks the same size on
screens with different scaling (F15-4). Pinned images live in memory only.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import (
    QCloseEvent,
    QColor,
    QContextMenuEvent,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QWheelEvent,
)
from PySide6.QtWidgets import QMenu, QWidget

from snapocr.annotate import zoom_percent, zoom_rect
from snapocr.geometry import Rect
from snapocr.gui import clipboard
from snapocr.gui.imageops import encode_png

_BORDER = QColor(74, 144, 226)
_NOTCH = 120  # angleDelta of one wheel notch


class PinWindow(QWidget):
    closed = Signal()

    def __init__(self, image: QImage, geometry: Rect, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._image = image
        self._base = (geometry.w, geometry.h)
        self._zoom = 100
        self._grab: QPointF | None = None  # mouse offset inside the window while dragging
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        # A Tool window on a Mac hides while another app is active; a pin is for looking at from there (M9).
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.setGeometry(QRect(geometry.x, geometry.y, geometry.w, geometry.h))
        self.menu = QMenu(self)
        self.menu.addAction("复制图片", lambda: clipboard.set_png(encode_png(self._image)))
        self.menu.addAction("关闭", self.close)

    @property
    def image(self) -> QImage:
        return self._image

    @property
    def zoom(self) -> int:
        """Size in percent of the original selection (F15-2)."""
        return self._zoom

    # --- input -------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._grab = event.globalPosition() - QPointF(self.pos())

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._grab is not None:
            self.move((event.globalPosition() - self._grab).toPoint())

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._grab = None

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        self.close()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()

    def wheelEvent(self, event: QWheelEvent) -> None:
        zoom = zoom_percent(self._zoom, event.angleDelta().y() // _NOTCH)
        if zoom == self._zoom:
            return
        g = self.geometry()
        at = event.globalPosition()
        r = zoom_rect(Rect(g.x(), g.y(), g.width(), g.height()), (at.x(), at.y()), self._base, zoom)
        self._zoom = zoom
        self.setGeometry(QRect(r.x, r.y, r.w, r.h))

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        self.menu.popup(event.globalPos())

    def closeEvent(self, event: QCloseEvent) -> None:
        super().closeEvent(event)
        self.closed.emit()  # Qt sends no second close event to a closed window

    # --- painting ----------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawImage(QRectF(self.rect()), self._image)
        painter.setPen(QPen(_BORDER, 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        painter.end()
