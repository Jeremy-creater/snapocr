"""Translation window (F8-1 to F8-4, F19-2, F19-5, F19-6).

One window is reused for screenshot translations and typed text. Per job it
goes Translating -> Done | Failed; events of older jobs are ignored, so a slow
earlier translation never overwrites a newer one. Esc hides it.

The source box is editable (M6 plan D5, D6): a new job fills it, the result
of the same job only fills the translation box, so an edit made while the
model works survives. ``Ctrl+Enter`` or the "翻译" button asks for the source
box to be translated with the chosen target (``translate_requested``).
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QRect, Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from snapocr.actions.outcomes import Done, Failed, PopupState, Translating
from snapocr.geometry import Rect, place_popup
from snapocr.gui import clipboard

TRANSLATING_TEXT = "翻译中…"
DEFAULT_SIZE = (420, 260)
TARGETS = (("自动", None), ("译成中文", "zh"), ("译成英文", "en"))
_ENTER_KEYS = (Qt.Key.Key_Return, Qt.Key.Key_Enter)


class TranslationPopup(QWidget):
    translate_requested = Signal(str, object)  # (source text, target: None | "zh" | "en")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._job_id: int | None = None
        self._state: PopupState | None = None
        self._shown_source = ""  # the source box as last filled, to tell whether it was edited
        self.setWindowTitle("snapocr 翻译")
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)

        self.source_view = QPlainTextEdit()
        self.translation_view = QPlainTextEdit(readOnly=True)
        self.copy_source_button = QPushButton("复制原文")
        self.copy_translation_button = QPushButton("复制译文")
        self.target_box = QComboBox()
        for text, target in TARGETS:
            self.target_box.addItem(text, target)
        self.translate_button = QPushButton("翻译")
        self.translate_button.setToolTip("翻译原文（Ctrl+Enter）")
        # Copy the translation from the state: QPlainTextEdit may normalise line breaks.
        self.copy_source_button.clicked.connect(lambda: clipboard.set_text(self.source_text()))
        self.copy_translation_button.clicked.connect(lambda: clipboard.set_text(self._state.translation))
        self.translate_button.clicked.connect(self._request)
        self.source_view.textChanged.connect(self._update_buttons)
        self.source_view.installEventFilter(self)

        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel("原文"))
        row.addStretch(1)
        row.addWidget(self.copy_source_button)
        layout.addLayout(row)
        layout.addWidget(self.source_view, 1)
        row = QHBoxLayout()
        row.addWidget(self.target_box)
        row.addStretch(1)
        row.addWidget(self.translate_button)
        layout.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel("译文"))
        row.addStretch(1)
        row.addWidget(self.copy_translation_button)
        layout.addLayout(row)
        layout.addWidget(self.translation_view, 1)
        self.resize(*DEFAULT_SIZE)
        self._render(fill_source=True)

    @property
    def job_id(self) -> int | None:
        return self._job_id

    @property
    def state(self) -> PopupState | None:
        return self._state

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

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)
