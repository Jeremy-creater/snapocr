"""The settings window (PRD F11-1, F11-3; M3 plan D4, D5).

Only shows and collects values: the controller checks them, writes the file,
re-registers the hotkeys and calls ``finish()`` when saving worked, or
``show_problems()`` when it did not. Hidden, not destroyed, when closed.

"浏览…" opens a ``QFileDialog`` instance with ``open()`` (M4 plan D27), kept
in ``folder_dialog``, so tests drive the real dialog instead of a static call.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from snapocr.actions.messages import COMMAND_LABELS
from snapocr.commands import Command
from snapocr.config.schema import HOTKEY_COMMANDS
from snapocr.config.settings import Settings
from snapocr.gui.hotkey_edit import HotkeyEdit
from snapocr.theme import THEME_LABELS, glass_note

_TARGET_LANGS = (
    ("自动（中文译成英文，其他译成中文）", "auto"),
    ("译成中文", "zh"),
    ("译成英文", "en"),
)
_SWITCHES = (
    ("paragraphs", "把自动折行的行合并成段落"),
    ("spacing", "在汉字和英文字母、数字之间加空格"),
    ("punctuation", "中文里的半角标点转成全角"),
)


class SettingsWindow(QWidget):
    save_requested = Signal(object, bool)  # Settings, start at login
    advanced_requested = Signal()
    closed = Signal()

    def __init__(self, parent: QWidget | None = None, *, platform: str = "win32") -> None:
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle("snapocr 设置")
        self.setMinimumWidth(440)

        hotkeys = QGroupBox("热键")
        form = QFormLayout(hotkeys)
        self.hotkey_edits: dict[Command, HotkeyEdit] = {}
        self._labels: dict[Command, QLabel] = {}
        for command in HOTKEY_COMMANDS:
            edit = HotkeyEdit(platform=platform)
            edit.rejected.connect(lambda reason, c=command: self.show_problems([f"{COMMAND_LABELS[c]}：{reason}"]))
            edit.hotkey_changed.connect(lambda _: self.show_problems([]))
            label = QLabel(COMMAND_LABELS[command])
            form.addRow(label, edit)
            self.hotkey_edits[command] = edit
            self._labels[command] = label
        self.hint_label = QLabel("点一下输入框，再按下新的组合键。设置窗口打开时，全局热键暂停。")
        self.hint_label.setWordWrap(True)
        form.addRow(self.hint_label)

        general = QGroupBox("常规")
        self.autostart_box = QCheckBox("开机时自动启动 snapocr")
        self.show_text_box = QCheckBox("OCR 完成的通知里显示识别出的文字")  # F11-8
        # F17-2: where the capture toolbar's "保存" puts screenshots.
        self.save_dir_label = QLabel("截图保存到")
        self.save_dir_edit = QLineEdit()
        self.browse_button = QPushButton("浏览…")
        self.browse_button.clicked.connect(self._browse)
        self.folder_dialog: QFileDialog | None = None
        save_dir_row = QHBoxLayout()
        save_dir_row.addWidget(self.save_dir_label)
        save_dir_row.addWidget(self.save_dir_edit, 1)
        save_dir_row.addWidget(self.browse_button)
        general_layout = QVBoxLayout(general)
        general_layout.addWidget(self.autostart_box)
        general_layout.addWidget(self.show_text_box)
        general_layout.addLayout(save_dir_row)
        # F20-2: the translation window's theme, with why glass falls back (F20-4).
        self.theme_label = QLabel("窗口风格")
        self.theme_box = QComboBox()
        for value, text in THEME_LABELS.items():
            self.theme_box.addItem(text, value)
        self.theme_note = QLabel()
        self.theme_note.setWordWrap(True)
        self.theme_note.hide()
        self._glass_problem: str | None = None
        self.theme_box.currentIndexChanged.connect(self._update_theme_note)
        theme_row = QHBoxLayout()
        theme_row.addWidget(self.theme_label)
        theme_row.addWidget(self.theme_box, 1)
        general_layout.addLayout(theme_row)
        general_layout.addWidget(self.theme_note)

        translate = QGroupBox("翻译")
        tform = QFormLayout(translate)
        self.target_lang_box = QComboBox()
        for text, value in _TARGET_LANGS:
            self.target_lang_box.addItem(text, value)
        # F11-7: pick a model the service lists, or type any name.
        self.model_box = QComboBox()
        self.model_box.setEditable(True)
        self.model_box.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.model_edit: QLineEdit = self.model_box.lineEdit()
        self.models_hint = QLabel()
        self.models_hint.setWordWrap(True)
        self.models_hint.hide()
        tform.addRow("目标语言", self.target_lang_box)
        tform.addRow("模型名", self.model_box)
        tform.addRow(self.models_hint)

        tidy = QGroupBox("识别结果整理")
        tidy_layout = QVBoxLayout(tidy)
        self.switch_boxes: dict[str, QCheckBox] = {}
        for name, text in _SWITCHES:
            box = QCheckBox(text)
            tidy_layout.addWidget(box)
            self.switch_boxes[name] = box

        self.problems_label = QLabel()
        self.problems_label.setWordWrap(True)
        self.problems_label.setStyleSheet("color: #c42b1c;")
        self.problems_label.hide()

        self.advanced_button = QPushButton("高级设置（打开配置文件）")
        self.save_button = QPushButton("保存")
        self.save_button.setDefault(True)
        self.cancel_button = QPushButton("取消")
        self.advanced_button.clicked.connect(self.advanced_requested)
        self.save_button.clicked.connect(self._save)
        self.cancel_button.clicked.connect(self.close)
        buttons = QHBoxLayout()
        buttons.addWidget(self.advanced_button)
        buttons.addStretch(1)
        buttons.addWidget(self.save_button)
        buttons.addWidget(self.cancel_button)

        layout = QVBoxLayout(self)
        for group in (hotkeys, general, translate, tidy):
            layout.addWidget(group)
        layout.addWidget(self.problems_label)
        layout.addLayout(buttons)

    def hotkey_label(self, command: Command) -> str:
        return self._labels[command].text()

    def load(self, settings: Settings, autostart: bool) -> None:
        """Show ``settings``; the model list holds only the current model until ``set_models``."""
        for command, edit in self.hotkey_edits.items():
            edit.set_hotkey(settings.hotkeys.get(command))
        self.autostart_box.setChecked(autostart)
        self.show_text_box.setChecked(settings.show_text)
        self.save_dir_edit.setText(str(settings.save_dir))
        self.theme_box.setCurrentIndex(self.theme_box.findData(settings.theme))
        self.target_lang_box.setCurrentIndex(self.target_lang_box.findData(settings.target_lang))
        self.model_edit.setText(settings.model)
        self.set_models((), None)
        for name, box in self.switch_boxes.items():
            box.setChecked(getattr(settings, name))
        self.show_problems([])

    def set_models(self, models: Sequence[str], hint: str | None) -> None:
        """F11-7: list ``models``; the text in the box now stays the current model (and in the list)."""
        current = self.model_box.currentText()
        self.model_box.clear()
        self.model_box.addItems(list(models) if current in models else [current, *models])
        self.model_box.setCurrentText(current)
        self.models_hint.setText(hint or "")
        self.models_hint.setVisible(hint is not None)

    def set_glass_problem(self, problem: str | None) -> None:
        """F20-4: why acrylic cannot be used now (None: it can)."""
        self._glass_problem = problem
        self._update_theme_note()

    def _update_theme_note(self) -> None:
        note = glass_note(self.theme_box.currentData(), self._glass_problem)
        self.theme_note.setText(note or "")
        self.theme_note.setVisible(note is not None)

    def show_problems(self, problems: Sequence[str]) -> None:
        self.problems_label.setText("\n".join(problems))
        self.problems_label.setVisible(bool(problems))

    def _browse(self) -> None:
        if self.folder_dialog is None:
            self.folder_dialog = QFileDialog(self, "选择截图保存文件夹")
            self.folder_dialog.setFileMode(QFileDialog.FileMode.Directory)
            self.folder_dialog.setOption(QFileDialog.Option.ShowDirsOnly)
            self.folder_dialog.fileSelected.connect(lambda path: self.save_dir_edit.setText(str(Path(path))))
        self.folder_dialog.setDirectory(self.save_dir_edit.text().strip())
        self.folder_dialog.open()

    def finish(self) -> None:
        """Close after a successful save."""
        self.close()

    def _save(self) -> None:
        hotkeys = {c: e.hotkey() for c, e in self.hotkey_edits.items() if e.hotkey() is not None}
        switches = {name: box.isChecked() for name, box in self.switch_boxes.items()}
        settings = Settings(
            hotkeys=hotkeys,
            target_lang=self.target_lang_box.currentData(),
            model=self.model_box.currentText().strip(),
            show_text=self.show_text_box.isChecked(),
            save_dir=Path(self.save_dir_edit.text().strip()),
            theme=self.theme_box.currentData(),
            **switches,
        )
        self.save_requested.emit(settings, self.autostart_box.isChecked())

    def closeEvent(self, event: QCloseEvent) -> None:
        super().closeEvent(event)
        self.closed.emit()
