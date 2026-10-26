"""Last-results window (F10-1 to F10-4).

Shows one ``HistoryRecord`` at a time: thumbnail, raw OCR text, post-processed
text and translation, each with a copy button. Entries are numbered oldest = 1
to newest = n. Edits stay in the text boxes and are dropped when another entry
is shown; the history is never written to.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from snapocr.actions.history import ResultHistory
from snapocr.actions.outcomes import HistoryRecord
from snapocr.gui import clipboard
from snapocr.gui.imageops import decode_png, thumbnail

EMPTY_TEXT = "暂无结果"
NO_TRANSLATION = "（无）"
NO_IMAGE = "（截图无法显示）"
THUMB_MAX = (360, 200)


class LastResultWindow(QWidget):
    def __init__(self, history: ResultHistory, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._history = history
        self._records: tuple[HistoryRecord, ...] = ()  # oldest first
        self._index: int | None = None
        self.setWindowTitle("snapocr 上次结果")

        self.empty_label = QLabel(EMPTY_TEXT)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail_label = QLabel()
        self.thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.raw_view = QPlainTextEdit()
        self.text_view = QPlainTextEdit()
        self.translation_view = QPlainTextEdit()
        self.copy_raw_button = QPushButton("复制")
        self.copy_text_button = QPushButton("复制")
        self.copy_translation_button = QPushButton("复制")
        self.prev_button = QPushButton("上一条")
        self.next_button = QPushButton("下一条")
        self.position_label = QLabel()

        for button, view in (
            (self.copy_raw_button, self.raw_view),
            (self.copy_text_button, self.text_view),
            (self.copy_translation_button, self.translation_view),
        ):
            button.clicked.connect(lambda _=False, v=view: clipboard.set_text(v.toPlainText()))
        self.prev_button.clicked.connect(lambda: self._go(-1))
        self.next_button.clicked.connect(lambda: self._go(1))

        layout = QVBoxLayout(self)
        layout.addWidget(self.empty_label)
        layout.addWidget(self.thumbnail_label)
        layout.addWidget(self.error_label)
        for title, view, button in (
            ("OCR 原文", self.raw_view, self.copy_raw_button),
            ("处理后文本", self.text_view, self.copy_text_button),
            ("译文", self.translation_view, self.copy_translation_button),
        ):
            row = QHBoxLayout()
            row.addWidget(QLabel(title))
            row.addStretch(1)
            row.addWidget(button)
            layout.addLayout(row)
            layout.addWidget(view, 1)
        nav = QHBoxLayout()
        nav.addWidget(self.prev_button)
        nav.addStretch(1)
        nav.addWidget(self.position_label)
        nav.addStretch(1)
        nav.addWidget(self.next_button)
        layout.addLayout(nav)
        self.resize(480, 640)
        self._render()

    @property
    def index(self) -> int | None:
        return self._index

    def show_latest(self) -> None:
        """F10-1: open on the newest entry."""
        self._refresh()
        self.show()
        self.raise_()
        self.activateWindow()

    def on_new_result(self) -> None:
        """A new record was pushed; jump to it if the window is open."""
        if self.isVisible():
            self._refresh()

    def _refresh(self) -> None:
        self._records = tuple(reversed(self._history.snapshot()))
        self._index = len(self._records) - 1 if self._records else None
        self._render()

    def _go(self, step: int) -> None:
        # Buttons are disabled at the ends, so the new index is always in range.
        self._index += step
        self._render()

    def _render(self) -> None:
        empty = self._index is None
        self.empty_label.setVisible(empty)
        self.thumbnail_label.setVisible(not empty)
        record = None if empty else self._records[self._index]
        self._show_thumbnail(record)
        self.raw_view.setPlainText("" if record is None else record.raw)
        self.text_view.setPlainText("" if record is None else record.text)
        has_translation = record is not None and record.translation is not None
        if record is None:
            self.translation_view.setPlainText("")
        else:
            self.translation_view.setPlainText(record.translation if has_translation else NO_TRANSLATION)
        self.translation_view.setReadOnly(not has_translation)
        self.error_label.setText("" if record is None or record.error is None else f"错误：{record.error}")
        self.error_label.setVisible(record is not None and record.error is not None)
        self.copy_raw_button.setEnabled(not empty)
        self.copy_text_button.setEnabled(not empty)
        self.copy_translation_button.setEnabled(has_translation)
        n = len(self._records)
        self.position_label.setText("" if empty else f"{self._index + 1} / {n}")
        self.prev_button.setEnabled(not empty and self._index > 0)
        self.next_button.setEnabled(not empty and self._index < n - 1)

    def _show_thumbnail(self, record: HistoryRecord | None) -> None:
        self.thumbnail_label.setPixmap(QPixmap())
        self.thumbnail_label.setText("")
        if record is None:
            return
        try:
            image = decode_png(record.png)
        except ValueError:
            self.thumbnail_label.setText(NO_IMAGE)
            return
        self.thumbnail_label.setPixmap(QPixmap.fromImage(thumbnail(image, THUMB_MAX)))

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)
