"""M9 WI-8: recording real key presses on the Mac (gui-mac lane; PRD F23-2, F11-2).

Pinned here:
- Real presses of Option+1, Control+Option+F5 and Shift+Command+S record
  those hotkeys: Qt's swapped modifiers and the Carbon key codes line up.
- Command+Q while the field has focus records ⌘Q and does not quit snapocr
  (the Cocoa menu's key equivalent does not take it first; M9 plan WI-3 item 7).
"""

import ctypes

import pytest
from PySide6.QtWidgets import QApplication

from snapocr.gui.hotkey_edit import HotkeyEdit
from snapocr.gui.platform.mac import _cocoa as c
from snapocr.gui.platform.mac import kit
from snapocr.hotkeys import parse_hotkey
from support.mac_input import press_combo

pytestmark = pytest.mark.gui


@pytest.fixture
def field(qtbot, qapp):
    kit.prepare_app(qapp)  # a menu bar app, as snapocr runs
    edit = HotkeyEdit(platform="darwin")
    qtbot.addWidget(edit)
    edit.show()
    c.send(c.ns_app(), "activateIgnoringOtherApps:", True, argtypes=(ctypes.c_bool,), restype=None)
    edit.activateWindow()
    edit.setFocus()
    qtbot.waitUntil(edit.hasFocus, timeout=2000)
    return edit


@pytest.mark.parametrize(("text", "shown"), [("Alt+1", "⌥1"), ("Ctrl+Alt+F5", "⌃⌥F5"), ("Shift+Cmd+S", "⇧⌘S")])
def test_real_presses_record(qtbot, field, text, shown):
    hk = parse_hotkey(text, platform="darwin")
    with qtbot.waitSignal(field.hotkey_changed, timeout=2000) as got:
        press_combo(hk.mods, hk.vk)
    assert got.args == [hk]
    assert field.text() == shown


def test_command_q_is_recorded_not_quit(qtbot, field):
    quits = []
    QApplication.instance().aboutToQuit.connect(lambda: quits.append(True))
    hk = parse_hotkey("Cmd+Q", platform="darwin")
    with qtbot.waitSignal(field.hotkey_changed, timeout=2000) as got:
        press_combo(hk.mods, hk.vk)
    qtbot.wait(300)
    assert got.args == [hk]
    assert field.text() == "⌘Q"
    assert quits == [] and field.isVisible()
