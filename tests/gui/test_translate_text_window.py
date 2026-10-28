"""M6 WI-5: Alt+4 opens the translation window for typed text (PRD F19-1, F19-3; plan D11).

Pinned here: the hotkey, the tray menu item "文字翻译" and ``run()`` all show
the window centred in the work area of the screen under the mouse when it was
hidden, leave it where it is when it is showing, give it focus with all of
the source box selected, and take no capture. The text stays when it is hidden.

Uses the controller harness of ``test_controller.py``.
"""

import pytest
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QCursor, QGuiApplication

from snapocr.commands import Command
from snapocr.geometry import Rect, center_in
from snapocr.hotkeys import hotkey_id
from support import qt_input as qi
from test_controller import became_active, clipboard, make  # noqa: F401 (fixtures)


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


def test_translate_text_selects_the_source_and_keeps_it(make, qtbot):
    h = make()
    popup = h.controller.popup
    h.controller.run(Command.TRANSLATE_TEXT)
    popup.source_view.setPlainText("上次输入的文字")
    qi.key(popup, Qt.Key.Key_Escape)
    assert not popup.isVisible()
    h.controller.run(Command.TRANSLATE_TEXT)
    assert popup.source_view.toPlainText() == "上次输入的文字"
    cursor = popup.source_view.textCursor()
    assert (cursor.selectionStart(), cursor.selectionEnd()) == (0, len("上次输入的文字"))


def test_translate_text_leaves_a_showing_window_where_it_is(make, qtbot):
    h = make()
    popup = h.controller.popup
    h.controller.run(Command.TRANSLATE_TEXT)
    popup.move(popup.x() + 37, popup.y() + 11)
    where = popup.geometry()
    h.controller.run(Command.TRANSLATE_TEXT)
    assert popup.geometry() == where
