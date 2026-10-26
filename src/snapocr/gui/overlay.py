"""Frozen-screen selection overlay, one window per screen (F6-1, F6-3, F6-4, F6-5; plan D4).

Each overlay shows its screen's part of the capture, dimmed, and lets the user
drag a selection, then adjust it (handles, move, re-select) and confirm with
Enter or a double click inside. All coordinates are physical pixels; the
geometry rules live in ``snapocr.geometry`` (WI-3). A selection never leaves
the screen it started on.
"""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QObject, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QKeyEvent, QMouseEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QWidget

from snapocr.geometry import (
    Handle,
    Point,
    Rect,
    ScreenInfo,
    hit_handle,
    is_cancel_size,
    local_to_physical,
    move,
    physical_to_local,
    resize,
    selection_rect,
)

HANDLE_SIZE = 7  # logical px, drawn centred on corners and edge midpoints
HANDLE_MARGIN = 5  # border and handles stay within this many logical px of the edges
_DIM = QColor(0, 0, 0, 110)
_BORDER = QColor(30, 144, 255)

_CURSORS = {
    Handle.NONE: Qt.CursorShape.CrossCursor,
    Handle.INSIDE: Qt.CursorShape.SizeAllCursor,
    Handle.NW: Qt.CursorShape.SizeFDiagCursor,
    Handle.SE: Qt.CursorShape.SizeFDiagCursor,
    Handle.NE: Qt.CursorShape.SizeBDiagCursor,
    Handle.SW: Qt.CursorShape.SizeBDiagCursor,
    Handle.N: Qt.CursorShape.SizeVerCursor,
    Handle.S: Qt.CursorShape.SizeVerCursor,
    Handle.W: Qt.CursorShape.SizeHorCursor,
    Handle.E: Qt.CursorShape.SizeHorCursor,
}


class OverlayState(Enum):
    SELECTING = "selecting"
    ADJUSTING = "adjusting"
    FINISHED = "finished"


class SelectionOverlay(QWidget):
    selected = Signal(object)  # Rect, physical pixels
    cancelled = Signal()

    def __init__(self, frozen: QImage, screen: ScreenInfo, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        p = screen.physical
        if (frozen.width(), frozen.height()) != (p.w, p.h):
            raise ValueError(f"frozen image is {frozen.width()}x{frozen.height()}, screen {screen.name} is {p.w}x{p.h}")
        self._frozen = frozen
        self._screen = screen
        self._state = OverlayState.SELECTING
        self._rect: Rect | None = None
        # The drag in progress: (handle, press point, rect at press). Handle.NONE = new selection.
        self._drag: tuple[Handle, Point, Rect | None] | None = None
        self._tol = max(1, round(HANDLE_SIZE / 2 * screen.dpr))
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        logical = screen.logical
        self.setGeometry(QRect(logical.x, logical.y, logical.w, logical.h))

    @property
    def state(self) -> OverlayState:
        return self._state

    @property
    def selection(self) -> Rect | None:
        return self._rect

    def abandon(self) -> None:
        """Stop reacting to input without emitting anything (the session ended elsewhere)."""
        self._state = OverlayState.FINISHED
        self._drag = None

    # --- results -----------------------------------------------------------

    def _finish(self, rect: Rect | None) -> None:
        self.abandon()
        if rect is None or is_cancel_size(rect):
            self.cancelled.emit()
        else:
            self.selected.emit(rect)

    # --- input -------------------------------------------------------------

    def _point(self, event: QMouseEvent) -> Point:
        pos = event.position()
        return local_to_physical(self._screen, pos.x(), pos.y())

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._state is OverlayState.FINISHED:
            return
        if event.button() == Qt.MouseButton.RightButton:
            self._finish(None)
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        p = self._point(event)
        handle = Handle.NONE
        if self._state is OverlayState.ADJUSTING:
            handle = hit_handle(self._rect, p, self._tol)
        if handle is Handle.NONE:
            self._state = OverlayState.SELECTING
            self._rect = selection_rect(self._screen, p, p)
            self.setCursor(Qt.CursorShape.CrossCursor)
        self._drag = (handle, p, self._rect)
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._state is OverlayState.FINISHED:
            return
        p = self._point(event)
        if self._drag is None:
            if self._state is OverlayState.ADJUSTING:
                self.setCursor(_CURSORS[hit_handle(self._rect, p, self._tol)])
            return
        handle, start, start_rect = self._drag
        if handle is Handle.NONE:
            self._rect = selection_rect(self._screen, start, p)
        elif handle is Handle.INSIDE:
            self._rect = move(start_rect, p[0] - start[0], p[1] - start[1], self._screen)
        else:
            self._rect = resize(start_rect, handle, p, self._screen)
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._state is OverlayState.FINISHED or event.button() != Qt.MouseButton.LeftButton or self._drag is None:
            return
        self.mouseMoveEvent(event)
        handle = self._drag[0]
        self._drag = None
        if handle is Handle.NONE:
            if is_cancel_size(self._rect):
                self._finish(None)
                return
            self._state = OverlayState.ADJUSTING
        self.update()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if self._state is not OverlayState.ADJUSTING:
            return
        if hit_handle(self._rect, self._point(event), self._tol) is Handle.INSIDE:
            self._finish(self._rect)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if self._state is OverlayState.FINISHED:
            return
        if event.key() == Qt.Key.Key_Escape:
            self._finish(None)
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._state is OverlayState.ADJUSTING and self._drag is None:
                self._finish(self._rect)

    # --- painting ----------------------------------------------------------

    def _local_rect(self, rect: Rect) -> QRectF:
        x0, y0 = physical_to_local(self._screen, rect.x, rect.y)
        x1, y1 = physical_to_local(self._screen, rect.x + rect.w, rect.y + rect.h)
        return QRectF(QPointF(x0, y0), QPointF(x1, y1))

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        full = QRectF(self.rect())
        painter.drawImage(full, self._frozen, QRectF(self._frozen.rect()))
        painter.fillRect(full, _DIM)
        if self._rect is not None and self._state is not OverlayState.FINISHED:
            sel = self._local_rect(self._rect)
            source = QRectF(
                self._rect.x - self._screen.physical.x, self._rect.y - self._screen.physical.y, self._rect.w, self._rect.h
            )
            painter.drawImage(sel, self._frozen, source)
            painter.setPen(QPen(_BORDER, 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(sel)
            if self._state is OverlayState.ADJUSTING:
                self._paint_handles(painter, sel)
        painter.end()

    def _paint_handles(self, painter: QPainter, sel: QRectF) -> None:
        painter.setBrush(_BORDER)
        half = HANDLE_SIZE / 2
        xs = (sel.left(), sel.center().x(), sel.right())
        ys = (sel.top(), sel.center().y(), sel.bottom())
        for i, x in enumerate(xs):
            for j, y in enumerate(ys):
                if i == 1 and j == 1:
                    continue
                painter.drawRect(QRectF(x - half, y - half, HANDLE_SIZE, HANDLE_SIZE))


class OverlaySession(QObject):
    """All overlays of one capture; the first result ends the session (emitted once)."""

    result = Signal(object)  # Rect, or None when cancelled

    def __init__(self, overlays: list[SelectionOverlay], parent: QObject | None = None) -> None:
        super().__init__(parent)
        if not overlays:
            raise ValueError("a session needs at least one overlay")
        self._overlays = list(overlays)
        self._started = False
        self._finished = False
        for overlay in self._overlays:
            overlay.selected.connect(self._on_result)
            overlay.cancelled.connect(lambda: self._on_result(None))

    @property
    def finished(self) -> bool:
        return self._finished

    def start(self) -> None:
        if self._started:
            raise RuntimeError("session already started")
        self._started = True
        for overlay in self._overlays:
            overlay.show()
        self._overlays[0].activateWindow()
        self._overlays[0].setFocus()

    def _on_result(self, rect: Rect | None) -> None:
        # Exactly once: abandon() makes every overlay inert before anything else can emit.
        self._finished = True
        for overlay in self._overlays:
            overlay.abandon()
            overlay.close()
        self.result.emit(rect)
