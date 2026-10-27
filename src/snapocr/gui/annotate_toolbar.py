"""The annotation toolbar shown next to a screenshot selection (PRD F14-1, F14-4, F14-6; M4 plan D12).

A child widget of the selection overlay, not a window of its own, so it never
takes focus from the overlay; its buttons take no keyboard focus either
(Enter and Esc belong to the overlay). Icons are drawn here with QPainter.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QFrame, QHBoxLayout, QToolButton, QWidget

from snapocr.annotate import COLOR_NAMES, DEFAULT_STYLE, LEVEL_NAMES, PALETTE, Style, Tool

ICON = 20
_INK = QColor("#333333")

_TOOLS = (
    (Tool.RECT, "tool-rect", "矩形"),
    (Tool.ELLIPSE, "tool-ellipse", "椭圆"),
    (Tool.ARROW, "tool-arrow", "箭头"),
    (Tool.TEXT, "tool-text", "文字"),
)


def _icon(draw: Callable[[QPainter], None]) -> QIcon:
    pixmap = QPixmap(ICON, ICON)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(_INK, 1.6))
    draw(painter)
    painter.end()
    return QIcon(pixmap)


def _glyph(text: str) -> Callable[[QPainter], None]:
    def draw(p: QPainter) -> None:
        font = QFont()
        font.setPixelSize(15)
        font.setBold(True)
        p.setFont(font)
        p.drawText(QRectF(0, 0, ICON, ICON), int(Qt.AlignmentFlag.AlignCenter), text)

    return draw


def _arrow(p: QPainter) -> None:
    p.drawLine(QPointF(4, 16), QPointF(15, 5))
    p.setBrush(_INK)
    p.drawPolygon(QPolygonF([QPointF(16, 4), QPointF(9, 6), QPointF(14, 11)]))


def _pushpin(p: QPainter) -> None:
    p.drawLine(QPointF(10, 12), QPointF(10, 18))
    p.drawLine(QPointF(5, 11.5), QPointF(15, 11.5))
    p.setBrush(_INK)
    p.drawRect(QRectF(7.5, 3, 5, 8))


_TOOL_ICONS: dict[Tool, Callable[[QPainter], None]] = {
    Tool.RECT: lambda p: p.drawRect(QRectF(3.5, 4.5, 13, 11)),
    Tool.ELLIPSE: lambda p: p.drawEllipse(QRectF(3.5, 4.5, 13, 11)),
    Tool.ARROW: _arrow,
    Tool.TEXT: _glyph("T"),
}


def _swatch(color: str) -> Callable[[QPainter], None]:
    def draw(p: QPainter) -> None:
        p.setPen(QPen(QColor("#888888"), 1))
        p.setBrush(QColor(color))
        p.drawRoundedRect(QRectF(3.5, 3.5, 13, 13), 2, 2)

    return draw


def _dot(level: int) -> Callable[[QPainter], None]:
    def draw(p: QPainter) -> None:
        r = 2 + 2 * level
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_INK)
        p.drawEllipse(QPointF(ICON / 2, ICON / 2), r, r)

    return draw


class AnnotateToolbar(QWidget):
    tool_changed = Signal(object)  # Tool | None
    style_changed = Signal(object)  # Style
    undo_requested = Signal()
    pin_requested = Signal()
    cancel_requested = Signal()
    done_requested = Signal()

    def __init__(self, style: Style = DEFAULT_STYLE, parent: QWidget | None = None, *, show_pin: bool = False) -> None:
        super().__init__(parent)
        self._style = style
        self._tool: Tool | None = None
        self.setAutoFillBackground(True)
        self.setStyleSheet(
            "AnnotateToolbar { background: #f7f7f7; border: 1px solid #c8c8c8; border-radius: 4px; }"
            "QToolButton { border: none; padding: 3px; border-radius: 3px; }"
            "QToolButton:checked { background: #d6e6fb; }"
            "QToolButton:hover { background: #e6e6e6; }"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 3, 6, 3)
        layout.setSpacing(2)
        self._tools: dict[Tool, QToolButton] = {}
        for tool, name, tip in _TOOLS:
            b = self._button(layout, name, tip, _icon(_TOOL_ICONS[tool]), checkable=True)
            b.clicked.connect(lambda _=False, t=tool: self._pick_tool(t))
            self._tools[tool] = b
        self._separator(layout)
        self._colors: list[QToolButton] = []
        for i, (color, label) in enumerate(zip(PALETTE, COLOR_NAMES, strict=True)):
            b = self._button(layout, f"color-{i}", f"颜色：{label}", _icon(_swatch(color)), checkable=True)
            b.setChecked(color == style.color)
            b.clicked.connect(lambda _=False, c=color: self._set_style(Style(c, self._style.level)))
            self._colors.append(b)
        self._levels: list[QToolButton] = []
        for level, label in enumerate(LEVEL_NAMES):
            b = self._button(layout, f"level-{level}", f"粗细：{label}", _icon(_dot(level)), checkable=True)
            b.setChecked(level == style.level)
            b.clicked.connect(lambda _=False, lv=level: self._set_style(Style(self._style.color, lv)))
            self._levels.append(b)
        self._separator(layout)
        self._undo = self._button(layout, "undo", "撤销（Ctrl+Z）", _icon(_glyph("↶")))
        self._undo.setEnabled(False)
        self._undo.clicked.connect(self.undo_requested)
        pin = self._button(layout, "pin", "贴图：钉在屏幕上", _icon(_pushpin))
        pin.setVisible(show_pin)
        pin.clicked.connect(self.pin_requested)
        self._button(layout, "cancel", "取消（Esc）", _icon(_glyph("✕"))).clicked.connect(self.cancel_requested)
        self._button(layout, "done", "完成：复制到剪贴板（Enter）", _icon(_glyph("✓"))).clicked.connect(
            self.done_requested
        )
        self.adjustSize()

    def _button(self, layout: QHBoxLayout, name: str, tip: str, icon: QIcon, *, checkable: bool = False) -> QToolButton:
        b = QToolButton(self)
        b.setObjectName(name)
        b.setToolTip(tip)
        b.setIcon(icon)
        b.setIconSize(QSize(ICON, ICON))
        b.setCheckable(checkable)
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout.addWidget(b)
        return b

    def _separator(self, layout: QHBoxLayout) -> None:
        line = QFrame(self)
        line.setFrameShape(QFrame.Shape.VLine)
        line.setStyleSheet("color: #d0d0d0;")
        layout.addWidget(line)

    @property
    def tool(self) -> Tool | None:
        return self._tool

    @property
    def style(self) -> Style:
        return self._style

    def set_undo_enabled(self, enabled: bool) -> None:
        self._undo.setEnabled(enabled)

    def _pick_tool(self, tool: Tool) -> None:
        self._tool = None if self._tool is tool else tool
        for t, b in self._tools.items():
            b.setChecked(t is self._tool)
        self.tool_changed.emit(self._tool)

    def _set_style(self, style: Style) -> None:
        changed = style != self._style
        self._style = style
        for color, b in zip(PALETTE, self._colors, strict=True):
            b.setChecked(color == style.color)
        for level, b in enumerate(self._levels):
            b.setChecked(level == style.level)
        if changed:
            self.style_changed.emit(style)
