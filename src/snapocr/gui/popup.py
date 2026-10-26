"""Translation popup (F8-1 to F8-4).

One popup is reused for every translate job. Per job it goes Translating ->
Done | Failed; events of older jobs are ignored, so a slow earlier
translation never overwrites a newer one. Esc hides it.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from snapocr.actions.outcomes import Done, Failed, PopupState, Translating
from snapocr.geometry import Rect, place_popup
from snapocr.gui import clipboard

TRANSLATING_TEXT = "翻译中…"
DEFAULT_SIZE = (420, 260)


class TranslationPopup(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._job_id: int | None = None
        self._state: PopupState | None = None
        self.setWindowTitle("snapocr 翻译")
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)

        self.source_view = QPlainTextEdit(readOnly=True)
        self.translation_view = QPlainTextEdit(readOnly=True)
        self.copy_source_button = QPushButton("复制原文")
        self.copy_translation_button = QPushButton("复制译文")
        # Copy from the state, not the views: QPlainTextEdit may normalise line breaks.
        # "Copy source" is enabled once there is a state, "copy translation" only in Done.
        self.copy_source_button.clicked.connect(lambda: clipboard.set_text(self._state.source))
        self.copy_translation_button.clicked.connect(lambda: clipboard.set_text(self._state.translation))

        layout = QVBoxLayout(self)
        for label, view, button in (
            ("原文", self.source_view, self.copy_source_button),
            ("译文", self.translation_view, self.copy_translation_button),
        ):
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            row.addStretch(1)
            row.addWidget(button)
            layout.addLayout(row)
            layout.addWidget(view, 1)
        self.resize(*DEFAULT_SIZE)
        self._render()

    @property
    def job_id(self) -> int | None:
        return self._job_id

    @property
    def state(self) -> PopupState | None:
        return self._state

    def apply(self, job_id: int, state: PopupState) -> bool:
        """Take ``state`` for ``job_id`` if the transition is legal; see the module docstring."""
        if self._job_id is None or job_id > self._job_id:
            self._job_id, self._state = job_id, state
            self._render()
            self.show()
            self.raise_()
            return True
        legal = job_id == self._job_id and isinstance(self._state, Translating) and isinstance(state, (Done, Failed))
        if legal:
            self._state = state
            self._render()
        return legal

    def place(self, anchor: Rect, available: Rect) -> None:
        """F8-1: next to the selection, inside ``available`` (logical coordinates)."""
        r = place_popup(anchor, (self.width(), self.height()), available)
        self.setGeometry(QRect(r.x, r.y, r.w, r.h))

    def _render(self) -> None:
        state = self._state
        if state is None:
            source, translation = "", ""
        elif isinstance(state, Translating):
            source, translation = state.source, TRANSLATING_TEXT
        elif isinstance(state, Done):
            source, translation = state.source, state.translation
        else:
            source, translation = state.source, state.message
        self.source_view.setPlainText(source)
        self.translation_view.setPlainText(translation)
        self.copy_source_button.setEnabled(state is not None)
        self.copy_translation_button.setEnabled(isinstance(state, Done))

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)
