"""M6 WI-5: Alt+4 opens the translation window for typed text (PRD F19-1, F19-3; plan D11).

Pinned here: the hotkey, the tray menu item "文字翻译" and ``run()`` all show
the window centred in the work area of the screen under the mouse when it was
hidden, leave it where it is when it is showing, give it focus in the source
box, and take no capture. Since PRD v1.4 (M6 WI-7) every Alt+4 gives a blank
window: source and translation cleared, hidden or showing; a translation still
on its way when it was cleared stays out of the window (its clipboard copy is
F19-7's business). The target box is kept (F19-6).

Uses the controller harness of ``test_controller.py``.
"""

import threading

import pytest
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QCursor, QGuiApplication

from snapocr.actions.outcomes import Done, Translating
from snapocr.commands import Command
from snapocr.geometry import Rect, center_in
from snapocr.hotkeys import hotkey_id
from snapocr.translators.types import TranslationResult
from support import qt_input as qi
from test_controller import WAIT, became_active, clipboard, make  # noqa: F401 (fixtures)


def cursor_work_area():
    screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
    g = screen.availableGeometry()
    return Rect(g.x(), g.y(), g.width(), g.height())


@pytest.mark.parametrize("via", ["hotkey", "menu", "run"])
def test_translate_text_opens_the_window_centred(make, qtbot, via):
    h = make()
    popup = h.controller.popup
    if via == "hotkey":
        h.controller.handle_hotkey(hotkey_id(Command.TRANSLATE_TEXT))
    elif via == "menu":
        next(a for a in h.controller.menu.actions() if a.text().split("\t")[0] == "文字翻译").trigger()
    else:
        h.controller.run(Command.TRANSLATE_TEXT)
    assert popup.isVisible()
    expected = center_in((popup.width(), popup.height()), cursor_work_area())
    assert popup.geometry() == QRect(expected.x, expected.y, expected.w, expected.h)
    assert became_active(qtbot, popup)
    assert h.capture.taken == []


def assert_blank(popup):
    assert popup.source_view.toPlainText() == ""
    assert popup.translation_view.toPlainText() == ""
    assert not popup.copy_source_button.isEnabled()
    assert not popup.copy_translation_button.isEnabled()
    assert popup.state is None


def translate_typed(h, text):
    popup = h.controller.popup
    popup.source_view.setPlainText(text)
    h.qtbot.mouseClick(popup.translate_button, Qt.MouseButton.LeftButton)


@pytest.mark.parametrize("hide_first", [True, False])
def test_translate_text_always_opens_blank(make, qtbot, clipboard, hide_first):
    h = make()
    popup = h.controller.popup
    h.controller.run(Command.TRANSLATE_TEXT)
    popup.target_box.setCurrentIndex(2)  # 译成英文
    translate_typed(h, "上次输入的文字")
    qtbot.waitUntil(lambda: isinstance(popup.state, Done), timeout=WAIT)
    if hide_first:
        qi.key(popup, Qt.Key.Key_Escape)
        assert not popup.isVisible()
    h.controller.handle_hotkey(hotkey_id(Command.TRANSLATE_TEXT))
    assert popup.isVisible()
    assert_blank(popup)
    assert popup.target == "en"  # F19-6: the choice is kept
    # Activation on a second show is not observable offscreen (a plain QWidget fails it
    # too); the first show's activation is pinned above, the real desktop by Jeremy.
    assert popup.focusWidget() is popup.source_view
    assert clipboard.text() == "en:T(上次输入的文字)"  # clearing the window leaves the clipboard alone


def test_translate_text_clears_a_screenshot_translation(make, qtbot):
    h = make()
    popup = h.controller.popup
    h.controller.run(Command.TRANSLATE)
    h.select(100, 100, 300, 160)
    qtbot.waitUntil(lambda: isinstance(popup.state, Done), timeout=WAIT)
    where = popup.geometry()
    h.controller.run(Command.TRANSLATE_TEXT)
    assert_blank(popup)
    assert popup.geometry() == where


class GatedTranslator:
    def __init__(self):
        self.gate = threading.Event()

    def translate(self, text, target=None):
        self.gate.wait(30)
        return TranslationResult(f"T({text})", "en", False)


def test_a_translation_cleared_on_its_way_stays_out_of_the_window(make, qtbot, clipboard):
    translator = GatedTranslator()
    h = make(translator=translator)
    popup = h.controller.popup
    try:
        h.controller.run(Command.TRANSLATE_TEXT)
        translate_typed(h, "Hello")
        qtbot.waitUntil(lambda: popup.state == Translating("Hello"), timeout=WAIT)
        h.controller.run(Command.TRANSLATE_TEXT)
        assert_blank(popup)
    finally:
        translator.gate.set()
    qtbot.waitUntil(lambda: clipboard.text() == "T(Hello)", timeout=WAIT)  # F19-7 still holds
    assert_blank(popup)
    # The blank window translates the next text as usual.
    translate_typed(h, "Again")
    qtbot.waitUntil(lambda: popup.state == Done("Again", "T(Again)"), timeout=WAIT)
    assert popup.translation_view.toPlainText() == "T(Again)"


def test_translate_text_leaves_a_showing_window_where_it_is(make, qtbot):
    h = make()
    popup = h.controller.popup
    h.controller.run(Command.TRANSLATE_TEXT)
    popup.move(popup.x() + 37, popup.y() + 11)
    where = popup.geometry()
    h.controller.run(Command.TRANSLATE_TEXT)
    assert popup.geometry() == where
