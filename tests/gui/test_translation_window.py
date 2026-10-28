"""M6 WI-3: the translation window's editable source, target box and translate trigger (PRD F19-2, F19-5, F19-6; plan D5, D6).

Pinned here:
- The source box is editable, the translation box read-only.
- The target box offers 自动 / 中文 / 英文 (None / "zh" / "en"; v1.6, was 译成中文 / 译成英文),
  starting at 自动.
- ``Ctrl+Enter`` in the source box (main or keypad Enter) and the "翻译"
  button emit ``translate_requested(text, target)``; blank text emits
  nothing; plain Enter is a line break. Unedited text is sent exactly as the
  state holds it.
- Within one job, ``Done`` / ``Failed`` leave the source box alone (the user
  may be editing); a new job fills it.
- "复制原文" copies the source box as it is now (edited or not) and is
  enabled whenever the source box has text.
- ``focus_source()`` selects all of the source box.
- Esc hides the window also while the source box has focus.
"""

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QGuiApplication, QKeyEvent, QTextCursor
from PySide6.QtWidgets import QApplication

from snapocr.actions.outcomes import Done, Failed, Translating
from snapocr.gui.popup import TranslationPopup

SRC = "今天天气很好"
TR = "The weather is nice today"
CTRL = Qt.KeyboardModifier.ControlModifier


@pytest.fixture
def window(qtbot):
    widget = TranslationPopup()
    qtbot.addWidget(widget)
    widget.show()
    return widget


@pytest.fixture
def clipboard(qapp):
    cb = QGuiApplication.clipboard()
    cb.setText("sentinel")
    yield cb
    cb.clear()


def type_in(qtbot, window, text):
    """Type at the end of the source box. One key event per character, carrying the
    character as its text: ``qtbot.keyClicks`` crashes Qt on non-ASCII characters."""
    view = window.source_view
    view.setFocus()
    view.moveCursor(QTextCursor.MoveOperation.End)
    for ch in text:
        QApplication.sendEvent(view, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_unknown, Qt.KeyboardModifier.NoModifier, ch))


def test_source_is_editable_translation_is_not(window):
    assert not window.source_view.isReadOnly()
    assert window.translation_view.isReadOnly()


def test_target_box_choices(window):
    box = window.target_box
    assert [box.itemText(i) for i in range(box.count())] == ["自动", "中文", "英文"]  # PRD v1.6 F19-2 (M7 WI-5)
    assert [box.itemData(i) for i in range(box.count())] == [None, "zh", "en"]
    assert box.currentIndex() == 0
    assert window.target is None
    box.setCurrentIndex(2)
    assert window.target == "en"


@pytest.mark.parametrize("enter", [Qt.Key.Key_Return, Qt.Key.Key_Enter])
def test_ctrl_enter_requests_the_typed_text(qtbot, window, enter):
    type_in(qtbot, window, "Hello")
    with qtbot.waitSignal(window.translate_requested, timeout=1000) as blocker:
        qtbot.keyClick(window.source_view, enter, CTRL)
    assert blocker.args == ["Hello", None]
    assert window.source_view.toPlainText() == "Hello"  # no line break added


def test_button_requests_with_the_chosen_target(qtbot, window):
    type_in(qtbot, window, "你好")
    window.target_box.setCurrentIndex(1)
    with qtbot.waitSignal(window.translate_requested, timeout=1000) as blocker:
        qtbot.mouseClick(window.translate_button, Qt.MouseButton.LeftButton)
    assert blocker.args == ["你好", "zh"]


@pytest.mark.parametrize("text", ["", "   ", "\n\t"], ids=repr)
def test_blank_text_requests_nothing(qtbot, window, text):
    window.source_view.setPlainText(text)
    with qtbot.assertNotEmitted(window.translate_requested):
        qtbot.keyClick(window.source_view, Qt.Key.Key_Return, CTRL)
        qtbot.mouseClick(window.translate_button, Qt.MouseButton.LeftButton)


def test_plain_enter_is_a_line_break(qtbot, window):
    type_in(qtbot, window, "a")
    with qtbot.assertNotEmitted(window.translate_requested):
        qtbot.keyClick(window.source_view, Qt.Key.Key_Return)
    type_in(qtbot, window, "b")
    assert window.source_view.toPlainText() == "a\nb"


def test_unedited_source_is_sent_exactly(qtbot, window):
    window.apply(1, Done("a\r\nb", TR))
    with qtbot.waitSignal(window.translate_requested, timeout=1000) as blocker:
        qtbot.mouseClick(window.translate_button, Qt.MouseButton.LeftButton)
    assert blocker.args == ["a\r\nb", None]


def test_edited_source_is_sent_as_edited(qtbot, window):
    window.apply(1, Done(SRC, TR))
    type_in(qtbot, window, "吗")
    with qtbot.waitSignal(window.translate_requested, timeout=1000) as blocker:
        qtbot.keyClick(window.source_view, Qt.Key.Key_Return, CTRL)
    assert blocker.args == [SRC + "吗", None]


@pytest.mark.parametrize("end", [Done(SRC, TR), Failed(SRC, "翻译失败：连接不上")])
def test_result_of_the_same_job_keeps_the_edit(qtbot, window, end):
    window.apply(1, Translating(SRC))
    type_in(qtbot, window, "，改了")
    assert window.apply(1, end) is True
    assert window.source_view.toPlainText() == SRC + "，改了"
    expected = end.translation if isinstance(end, Done) else end.message
    assert window.translation_view.toPlainText() == expected


def test_new_job_fills_the_source_box(qtbot, window):
    window.apply(1, Done(SRC, TR))
    type_in(qtbot, window, "x")
    window.apply(2, Translating("新的原文"))
    assert window.source_view.toPlainText() == "新的原文"


def test_copy_source_copies_the_edit(qtbot, window, clipboard):
    window.apply(1, Done(SRC, TR))
    type_in(qtbot, window, "！")
    qtbot.mouseClick(window.copy_source_button, Qt.MouseButton.LeftButton)
    assert clipboard.text() == SRC + "！"


def test_copy_source_enabled_whenever_there_is_text(qtbot, window, clipboard):
    assert not window.copy_source_button.isEnabled()
    type_in(qtbot, window, "typed")
    assert window.copy_source_button.isEnabled()
    qtbot.mouseClick(window.copy_source_button, Qt.MouseButton.LeftButton)
    assert clipboard.text() == "typed"
    window.source_view.clear()
    assert not window.copy_source_button.isEnabled()


def test_focus_source_selects_all(window):
    window.source_view.setPlainText("第一行\n第二行")
    window.focus_source()
    cursor = window.source_view.textCursor()
    assert cursor.selectionStart() == 0
    assert cursor.selectionEnd() == len("第一行\n第二行")


def test_esc_in_the_source_box_hides(qtbot, window):
    type_in(qtbot, window, "abc")
    qtbot.keyClick(window.source_view, Qt.Key.Key_Escape)
    assert not window.isVisible()
