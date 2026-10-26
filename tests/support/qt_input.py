"""Hand-built mouse and key events delivered with sendEvent (plan R6, WI-14 onwards).

Positions are widget-local logical coordinates (floats allowed).
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication, QWidget

LEFT = Qt.MouseButton.LeftButton
RIGHT = Qt.MouseButton.RightButton
NONE = Qt.MouseButton.NoButton
_NO_MOD = Qt.KeyboardModifier.NoModifier


def _mouse(widget: QWidget, kind: QEvent.Type, x: float, y: float, button, buttons) -> None:
    pos = QPointF(x, y)
    QApplication.sendEvent(widget, QMouseEvent(kind, pos, widget.mapToGlobal(pos), button, buttons, _NO_MOD))


def press(widget: QWidget, x: float, y: float, button=LEFT) -> None:
    _mouse(widget, QEvent.Type.MouseButtonPress, x, y, button, button)


def move(widget: QWidget, x: float, y: float, buttons=LEFT) -> None:
    _mouse(widget, QEvent.Type.MouseMove, x, y, NONE, buttons)


def release(widget: QWidget, x: float, y: float, button=LEFT) -> None:
    _mouse(widget, QEvent.Type.MouseButtonRelease, x, y, button, NONE)


def double_click(widget: QWidget, x: float, y: float) -> None:
    """What Qt delivers for the second click of a double click: DblClick, then Release."""
    _mouse(widget, QEvent.Type.MouseButtonDblClick, x, y, LEFT, LEFT)
    release(widget, x, y)


def drag(widget: QWidget, x0: float, y0: float, x1: float, y1: float) -> None:
    press(widget, x0, y0)
    move(widget, (x0 + x1) / 2, (y0 + y1) / 2)
    move(widget, x1, y1)
    release(widget, x1, y1)


def key(widget: QWidget, k: Qt.Key) -> None:
    QApplication.sendEvent(widget, QKeyEvent(QEvent.Type.KeyPress, k, _NO_MOD))
    QApplication.sendEvent(widget, QKeyEvent(QEvent.Type.KeyRelease, k, _NO_MOD))
