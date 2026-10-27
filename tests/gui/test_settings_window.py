"""M3 WI-5: the settings window (PRD F11-1, F11-3 window side; M3 plan D4, D5). Offscreen.

Pinned here (beyond the plan text):
- Rows in this order: four hotkeys (截图, OCR, 翻译, 上次结果), start at login,
  target language (auto / zh / en), model name, the three post-processing switches.
- "保存" emits ``save_requested(Settings, autostart)``; the model name is
  stripped; a hotkey field left empty (the hotkey was disabled) is left out.
  Saving does not close the window: the controller calls ``finish()``.
- Problems show in one label, one per line; ``load`` and a newly recorded
  hotkey clear them; a rejected key shows "<动作>：<原因>".
- "取消", ``finish()`` and closing the window all hide it and emit ``closed``.
"""

import dataclasses

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from snapocr.commands import Command
from snapocr.config.schema import AppConfig, HOTKEY_COMMANDS
from snapocr.config.settings import Settings, settings_of
from snapocr.gui.settings_window import SettingsWindow
from snapocr.hotkeys import parse_hotkey

DEFAULTS = settings_of(AppConfig())
CUSTOM = Settings(
    hotkeys={Command.CAPTURE: parse_hotkey("Ctrl+F1"), Command.OCR: parse_hotkey("Ctrl+F2"),
             Command.TRANSLATE: parse_hotkey("Ctrl+F3")},
    paragraphs=False, spacing=True, punctuation=False, target_lang="en", model="qwen3:8b",
)


def key(widget, k, mods=Qt.KeyboardModifier.NoModifier):
    for kind in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
        QApplication.sendEvent(widget, QKeyEvent(kind, k, mods))


class Spy:
    def __init__(self, window):
        self.saved, self.closed, self.advanced = [], [], []
        window.save_requested.connect(lambda s, a: self.saved.append((s, a)))
        window.closed.connect(lambda: self.closed.append(True))
        window.advanced_requested.connect(lambda: self.advanced.append(True))


@pytest.fixture
def window(qtbot):
    w = SettingsWindow()
    qtbot.addWidget(w)
    w.load(DEFAULTS, False)
    w.show()
    qtbot.waitExposed(w)
    return w


def test_title_rows_and_hint(window):
    assert window.windowTitle() == "snapocr 设置"
    assert [window.hotkey_label(c) for c in HOTKEY_COMMANDS] == ["截图", "OCR", "翻译", "上次结果"]
    assert window.autostart_box.text() == "开机时自动启动 snapocr"
    assert [window.target_lang_box.itemData(i) for i in range(window.target_lang_box.count())] == ["auto", "zh", "en"]
    assert [b.text() for b in window.switch_boxes.values()] == [
        "把自动折行的行合并成段落",
        "在汉字和英文字母、数字之间加空格",
        "中文里的半角标点转成全角",
    ]
    assert list(window.switch_boxes) == ["paragraphs", "spacing", "punctuation"]
    assert "热键暂停" in window.hint_label.text()
    assert window.advanced_button.text() == "高级设置（打开配置文件）"
    assert (window.save_button.text(), window.cancel_button.text()) == ("保存", "取消")
    assert not window.problems_label.isVisible()


def test_load_shows_values(window):
    window.load(CUSTOM, True)
    assert [window.hotkey_edits[c].text() for c in HOTKEY_COMMANDS] == ["Ctrl+F1", "Ctrl+F2", "Ctrl+F3", ""]
    assert window.autostart_box.isChecked()
    assert window.target_lang_box.currentData() == "en"
    assert window.model_edit.text() == "qwen3:8b"
    assert [b.isChecked() for b in window.switch_boxes.values()] == [False, True, False]


def test_save_unchanged_emits_loaded_values(window):
    spy = Spy(window)
    window.load(CUSTOM, True)
    window.save_button.click()
    assert spy.saved == [(CUSTOM, True)]
    assert window.isVisible()  # the controller closes it with finish()
    assert spy.closed == []


def test_save_edited_values(window):
    spy = Spy(window)
    edit = window.hotkey_edits[Command.OCR]
    key(edit, Qt.Key.Key_Q, Qt.KeyboardModifier.AltModifier)
    window.autostart_box.setChecked(True)
    window.target_lang_box.setCurrentIndex(window.target_lang_box.findData("zh"))
    window.model_edit.setText("  qwen3:8b ")
    window.switch_boxes["spacing"].setChecked(False)
    window.save_button.click()
    hotkeys = dict(DEFAULTS.hotkeys) | {Command.OCR: parse_hotkey("Alt+Q")}
    assert spy.saved == [(dataclasses.replace(DEFAULTS, hotkeys=hotkeys, target_lang="zh", model="qwen3:8b",
                                              spacing=False), True)]


def test_problems_shown_and_cleared(window):
    window.show_problems(["第一个问题", "第二个问题"])
    assert window.problems_label.isVisible()
    assert window.problems_label.text() == "第一个问题\n第二个问题"
    window.show_problems([])
    assert not window.problems_label.isVisible()
    window.show_problems(["x"])
    window.load(DEFAULTS, False)
    assert not window.problems_label.isVisible()


def test_rejected_key_shows_problem_then_new_hotkey_clears(window):
    edit = window.hotkey_edits[Command.TRANSLATE]
    key(edit, Qt.Key.Key_Q)
    assert window.problems_label.isVisible()
    assert window.problems_label.text().startswith("翻译：")
    assert "Ctrl" in window.problems_label.text()
    key(edit, Qt.Key.Key_Q, Qt.KeyboardModifier.ControlModifier)
    assert not window.problems_label.isVisible()
    assert edit.text() == "Ctrl+Q"


def test_cancel_closes_without_saving(window):
    spy = Spy(window)
    window.cancel_button.click()
    assert not window.isVisible()
    assert spy.closed == [True]
    assert spy.saved == []


def test_close_and_finish_emit_closed(window, qtbot):
    spy = Spy(window)
    window.close()
    assert spy.closed == [True]
    window.show()
    qtbot.waitExposed(window)
    window.finish()
    assert not window.isVisible()
    assert spy.closed == [True, True]


def test_advanced_button(window):
    spy = Spy(window)
    window.advanced_button.click()
    assert spy.advanced == [True]
    assert window.isVisible()


# --- M3 WI-10: model name is an editable list (F11-7, plan D12) --------------------------
# ``load`` shows only the current model; the controller fills the list later with
# ``set_models``, which treats the text in the box at that moment as the current model.


def items(box):
    return [box.itemText(i) for i in range(box.count())]


def test_load_shows_only_the_current_model_in_an_editable_box(window):
    window.load(CUSTOM, False)
    assert window.model_box.isEditable()
    assert items(window.model_box) == ["qwen3:8b"]
    assert window.model_box.currentText() == "qwen3:8b"
    assert window.model_edit.text() == "qwen3:8b"
    assert not window.models_hint.isVisible()


def test_set_models_lists_them_and_keeps_the_current_one(window):
    window.load(CUSTOM, False)
    window.set_models(("hy-mt2:7b", "llama3:8b", "qwen3:8b"), None)
    assert items(window.model_box) == ["hy-mt2:7b", "llama3:8b", "qwen3:8b"]
    assert window.model_box.currentText() == "qwen3:8b"
    assert not window.models_hint.isVisible()


def test_current_model_missing_from_the_list_is_added_first(window):
    window.load(CUSTOM, False)
    window.set_models(("hy-mt2:7b",), None)
    assert items(window.model_box) == ["qwen3:8b", "hy-mt2:7b"]
    assert window.model_box.currentText() == "qwen3:8b"


def test_text_typed_before_the_list_arrives_is_kept(window):
    window.load(CUSTOM, False)
    window.model_edit.setText("gemma3:4b")
    window.set_models(("hy-mt2:7b", "qwen3:8b"), None)
    assert window.model_box.currentText() == "gemma3:4b"
    assert items(window.model_box) == ["gemma3:4b", "hy-mt2:7b", "qwen3:8b"]


def test_load_again_drops_the_old_list(window):
    window.load(CUSTOM, False)
    window.set_models(("a", "b", "qwen3:8b"), None)
    window.load(CUSTOM, False)
    assert items(window.model_box) == ["qwen3:8b"]


def test_picking_a_listed_model_is_saved(window):
    spy = Spy(window)
    window.load(CUSTOM, True)
    window.set_models(("hy-mt2:7b", "qwen3:8b"), None)
    window.model_box.setCurrentIndex(items(window.model_box).index("hy-mt2:7b"))
    window.save_button.click()
    assert spy.saved == [(dataclasses.replace(CUSTOM, model="hy-mt2:7b"), True)]


def test_typed_model_is_saved(window):
    spy = Spy(window)
    window.load(CUSTOM, True)
    window.set_models(("hy-mt2:7b", "qwen3:8b"), None)
    window.model_box.setEditText(" gemma3:4b ")
    window.save_button.click()
    assert spy.saved == [(dataclasses.replace(CUSTOM, model="gemma3:4b"), True)]


def test_models_hint_is_shown_and_cleared(window):
    window.load(CUSTOM, False)
    window.set_models((), "没能读取模型列表（翻译服务没有运行），可以直接输入模型名。")
    assert window.models_hint.isVisible()
    assert window.models_hint.text() == "没能读取模型列表（翻译服务没有运行），可以直接输入模型名。"
    assert items(window.model_box) == ["qwen3:8b"]
    window.set_models(("qwen3:8b",), None)
    assert not window.models_hint.isVisible()
    window.set_models((), "x")
    window.load(CUSTOM, False)
    assert not window.models_hint.isVisible()
