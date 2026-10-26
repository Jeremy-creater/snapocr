"""The settings window (PRD F11-1, F11-3; M3 plan D4, D5).

Only shows and collects values: the controller checks them, writes the file,
re-registers the hotkeys and calls ``finish()`` when saving worked, or
``show_problems()`` when it did not. Hidden, not destroyed, when closed.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
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

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle("snapocr 设置")
        self.setMinimumWidth(440)

        hotkeys = QGroupBox("热键")
        form = QFormLayout(hotkeys)
        self.hotkey_edits: dict[Command, HotkeyEdit] = {}
        self._labels: dict[Command, QLabel] = {}
        for command in HOTKEY_COMMANDS:
            edit = HotkeyEdit()
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
        QVBoxLayout(general).addWidget(self.autostart_box)

        translate = QGroupBox("翻译")
        tform = QFormLayout(translate)
        self.target_lang_box = QComboBox()
        for text, value in _TARGET_LANGS:
            self.target_lang_box.addItem(text, value)
        self.model_edit = QLineEdit()
        tform.addRow("目标语言", self.target_lang_box)
        tform.addRow("模型名", self.model_edit)

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
        for command, edit in self.hotkey_edits.items():
            edit.set_hotkey(settings.hotkeys.get(command))
        self.autostart_box.setChecked(autostart)
        self.target_lang_box.setCurrentIndex(self.target_lang_box.findData(settings.target_lang))
        self.model_edit.setText(settings.model)
        for name, box in self.switch_boxes.items():
            box.setChecked(getattr(settings, name))
        self.show_problems([])

    def show_problems(self, problems: Sequence[str]) -> None:
        self.problems_label.setText("\n".join(problems))
        self.problems_label.setVisible(bool(problems))

    def finish(self) -> None:
        """Close after a successful save."""
        self.close()

    def _save(self) -> None:
        hotkeys = {c: e.hotkey() for c, e in self.hotkey_edits.items() if e.hotkey() is not None}
        switches = {name: box.isChecked() for name, box in self.switch_boxes.items()}
        settings = Settings(
            hotkeys=hotkeys,
            target_lang=self.target_lang_box.currentData(),
            model=self.model_edit.text().strip(),
            **switches,
        )
        self.save_requested.emit(settings, self.autostart_box.isChecked())

    def closeEvent(self, event: QCloseEvent) -> None:
        super().closeEvent(event)
        self.closed.emit()
