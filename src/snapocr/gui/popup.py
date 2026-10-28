"""Translation window (F8-1 to F8-4, F19-2, F19-5, F19-6).

One window is reused for screenshot translations and typed text. Per job it
goes Translating -> Done | Failed; events of older jobs are ignored, so a slow
earlier translation never overwrites a newer one. Esc hides it.

The source box is editable (M6 plan D5, D6): a new job fills it, the result
of the same job only fills the translation box, so an edit made while the
model works survives. ``Ctrl+Enter`` or the "翻译" button asks for the source
box to be translated with the chosen target (``translate_requested``).

Frameless since M7 (F20-5, plan D8): it paints its own rounded fill; the top
``TITLE_HEIGHT`` pixels drag the window and the outer ``EDGE`` pixels resize
it, through the system (``startSystemMove`` / ``startSystemResize``) or, when
the platform refuses (offscreen), by following the mouse itself.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QIcon,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from snapocr.actions.outcomes import Done, Failed, PopupState, Translating
from snapocr.geometry import Rect, place_popup, resize_edges, resized
from snapocr.gui import clipboard
from snapocr.gui.segmented import SegmentedControl
from snapocr.theme import FONT_FAMILIES, PALETTES, Color, Look, stylesheet

TRANSLATING_TEXT = "翻译中…"
DEFAULT_SIZE = (420, 260)
TARGETS = (("自动", None), ("中文", "zh"), ("英文", "en"))  # v1.6 (F19-2, F20-5)
MIN_SIZE = (320, 220)  # F20-5
TITLE_HEIGHT = 40  # the drag area at the top
EDGE = 6  # the resize band along the border
RADIUS = 12
_L, _T, _R, _B = "left", "top", "right", "bottom"
_QT_EDGES = {_L: Qt.Edge.LeftEdge, _T: Qt.Edge.TopEdge, _R: Qt.Edge.RightEdge, _B: Qt.Edge.BottomEdge}
_CURSORS = {
    frozenset(): Qt.CursorShape.ArrowCursor,
    frozenset({_L}): Qt.CursorShape.SizeHorCursor,
    frozenset({_R}): Qt.CursorShape.SizeHorCursor,
    frozenset({_T}): Qt.CursorShape.SizeVerCursor,
    frozenset({_B}): Qt.CursorShape.SizeVerCursor,
    frozenset({_L, _T}): Qt.CursorShape.SizeFDiagCursor,
    frozenset({_R, _B}): Qt.CursorShape.SizeFDiagCursor,
    frozenset({_R, _T}): Qt.CursorShape.SizeBDiagCursor,
    frozenset({_L, _B}): Qt.CursorShape.SizeBDiagCursor,
}
_ENTER_KEYS = (Qt.Key.Key_Return, Qt.Key.Key_Enter)


def _copy_icon(color: Color) -> QIcon:
    """Two overlapping rounded squares, drawn at 3x for high-DPI screens."""
    pixmap = QPixmap(36, 36)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(*color), 3.2))
    p.drawRoundedRect(QRectF(10.5, 10.5, 21, 21), 4.5, 4.5)
    p.drawPolyline([QPoint(25, 10), QPoint(25, 6), QPoint(6, 6), QPoint(6, 25), QPoint(10, 25)])
    p.end()
    pixmap.setDevicePixelRatio(3)
    return QIcon(pixmap)


class TranslationPopup(QWidget):
    translate_requested = Signal(str, object)  # (source text, target: None | "zh" | "en")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._job_id: int | None = None
        self._state: PopupState | None = None
        self._shown_source = ""  # the source box as last filled, to tell whether it was edited
        self._look = Look(PALETTES["light_solid"], False)
        # (start global mouse position, start geometry, grabbed edges; no edges = move)
        self._grab: tuple[QPoint, QRect, frozenset[str]] | None = None
        self.setWindowTitle("snapocr 翻译")
        self.setWindowFlags(
            Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setMinimumSize(*MIN_SIZE)

        self.title_label = QLabel("翻译", objectName="title")
        self.close_button = QPushButton("\u2715", self, objectName="close")  # over the title bar
        self.close_button.setFixedSize(28, 28)
        self.close_button.setToolTip("关闭（Esc）")
        self.close_button.clicked.connect(self.hide)
        self.source_view = QPlainTextEdit()
        self.translation_view = QPlainTextEdit(readOnly=True)
        self.source_view.setObjectName("source")
        self.translation_view.setObjectName("translation")
        self.copy_source_button = QPushButton("复制", objectName="copy", toolTip="复制原文")
        self.copy_translation_button = QPushButton("复制", objectName="copy", toolTip="复制译文")
        self.target_box = SegmentedControl()
        for text, target in TARGETS:
            self.target_box.addItem(text, target)
        self.translate_button = QPushButton("翻译", objectName="translate")
        self.translate_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hint_label = QLabel("Ctrl+Enter", objectName="hint")
        self.translate_button.setToolTip("翻译原文（Ctrl+Enter）")
        # Copy the translation from the state: QPlainTextEdit may normalise line breaks.
        self.copy_source_button.clicked.connect(lambda: clipboard.set_text(self.source_text()))
        self.copy_translation_button.clicked.connect(lambda: clipboard.set_text(self._state.translation))
        self.translate_button.clicked.connect(self._request)
        self.source_view.textChanged.connect(self._update_buttons)
        self.source_view.installEventFilter(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 0, 18, 18)
        title = QWidget()
        title.setFixedHeight(TITLE_HEIGHT)
        title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)  # presses reach the window
        row = QHBoxLayout(title)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.title_label)
        row.addStretch(1)
        layout.addWidget(title)
        row = QHBoxLayout()
        row.addWidget(QLabel("原文", objectName="muted"))
        row.addStretch(1)
        row.addWidget(self.copy_source_button)
        layout.addLayout(row)
        layout.addWidget(self.source_view, 1)
        row = QHBoxLayout()
        row.addWidget(self.target_box)
        row.addStretch(1)
        row.addWidget(self.hint_label)
        row.addSpacing(10)
        row.addWidget(self.translate_button)
        layout.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel("译文", objectName="muted"))
        row.addStretch(1)
        row.addWidget(self.copy_translation_button)
        layout.addLayout(row)
        layout.addWidget(self.translation_view, 1)
        font = QFont(self.font())
        font.setFamilies(list(FONT_FAMILIES))
        self.setFont(font)
        self.resize(*DEFAULT_SIZE)
        self.set_look(self._look)
        self._render(fill_source=True)

    @property
    def job_id(self) -> int | None:
        return self._job_id

    @property
    def state(self) -> PopupState | None:
        return self._state

    @property
    def look(self) -> Look:
        return self._look

    def set_look(self, look: Look) -> None:
        """F20: restyle now; turning acrylic on or off is the controller's part (``Glass``)."""
        self._look = look
        self.setStyleSheet(stylesheet(look.palette))
        icon = _copy_icon(look.palette.link)
        for button in (self.copy_source_button, self.copy_translation_button):
            button.setIcon(icon)
            button.setIconSize(QSize(12, 12))
        self.update()

    @property
    def target(self) -> str | None:
        """The chosen target language (F19-6): ``None`` follows the config."""
        return self.target_box.currentData()

    def source_text(self) -> str:
        """The source box; exactly the state's source while it is unedited."""
        text = self.source_view.toPlainText()
        if self._state is not None and text == self._shown_source:
            return self._state.source
        return text

    def focus_source(self) -> None:
        """F19-3: keyboard focus in the source box, all of it selected."""
        self.source_view.setFocus()
        self.source_view.selectAll()

    def clear(self) -> None:
        """F19-3 (v1.4): blank source and translation; the target box stays.

        The job id stays too, so the result of a job still on its way is
        refused by ``apply`` (no ``Translating`` state to finish).
        """
        self._state = None
        self.source_view.clear()
        self._shown_source = ""
        self._render(fill_source=False)

    def apply(self, job_id: int, state: PopupState) -> bool:
        """Take ``state`` for ``job_id`` if the transition is legal; see the module docstring."""
        if self._job_id is None or job_id > self._job_id:
            self._job_id, self._state = job_id, state
            self._render(fill_source=True)
            self.show()
            self.raise_()
            return True
        legal = job_id == self._job_id and isinstance(self._state, Translating) and isinstance(state, (Done, Failed))
        if legal:
            self._state = state
            self._render(fill_source=False)
        return legal

    def place(self, anchor: Rect, available: Rect) -> None:
        """F8-1: next to the selection, inside ``available`` (logical coordinates)."""
        self.setMinimumSize(min(MIN_SIZE[0], available.w), min(MIN_SIZE[1], available.h))
        r = place_popup(anchor, (self.width(), self.height()), available)
        self.setGeometry(QRect(r.x, r.y, r.w, r.h))

    def _render(self, *, fill_source: bool) -> None:
        state = self._state
        if state is None:
            translation = ""
        elif isinstance(state, Translating):
            translation = TRANSLATING_TEXT
        elif isinstance(state, Done):
            translation = state.translation
        else:
            translation = state.message
        if fill_source and state is not None:
            self.source_view.setPlainText(state.source)
            self._shown_source = self.source_view.toPlainText()
        self.translation_view.setPlainText(translation)
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.copy_source_button.setEnabled(bool(self.source_view.toPlainText()))
        self.copy_translation_button.setEnabled(isinstance(self._state, Done))

    def _request(self) -> None:
        text = self.source_text()
        if text.strip():  # F19-5: blank text asks for nothing
            self.translate_requested.emit(text, self.target)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if (
            watched is self.source_view
            and event.type() == QEvent.Type.KeyPress
            and event.key() in _ENTER_KEYS
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            self._request()
            return True
        return super().eventFilter(watched, event)

    # --- frame (F20-5) ------------------------------------------------------------------

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        side = self.close_button.width()
        self.close_button.move(self.width() - 18 - side, (TITLE_HEIGHT - side) // 2)
        self.close_button.raise_()

    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), RADIUS, RADIUS)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillPath(path, QColor(*self._look.palette.window))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        p.setPen(QPen(QColor(*self._look.palette.border), 1))
        p.drawPath(path)

    def _edges_at(self, pos: QPoint) -> frozenset[str]:
        return resize_edges(pos.x(), pos.y(), self.width(), self.height(), EDGE)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        pos = event.position().toPoint()
        edges = self._edges_at(pos)
        if event.button() != Qt.MouseButton.LeftButton or not (edges or pos.y() < TITLE_HEIGHT):
            super().mousePressEvent(event)
            return
        if not self._start_system_drag(edges):  # offscreen: follow the mouse ourselves
            self._grab = (event.globalPosition().toPoint(), self.geometry(), edges)

    def _start_system_drag(self, edges: frozenset[str]) -> bool:
        """Hand the move (no edges) or resize to the system; False when the platform refuses."""
        handle = self.windowHandle()
        if not edges:
            return handle.startSystemMove()
        flags = Qt.Edge(0)
        for edge in edges:
            flags |= _QT_EDGES[edge]
        return handle.startSystemResize(flags)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._grab is None:
            self.setCursor(_CURSORS[self._edges_at(event.position().toPoint())])
            super().mouseMoveEvent(event)
            return
        start, geometry, edges = self._grab
        delta = event.globalPosition().toPoint() - start
        if not edges:
            self.move(geometry.topLeft() + delta)
            return
        g = Rect(geometry.x(), geometry.y(), geometry.width(), geometry.height())
        r = resized(g, edges, delta.x(), delta.y(), (self.minimumWidth(), self.minimumHeight()))
        self.setGeometry(QRect(r.x, r.y, r.w, r.h))

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._grab = None
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)
