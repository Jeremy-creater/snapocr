"""M2 WI-19: global hotkeys on the real desktop (gui lane; PRD F5-3, F5-5; plan D3, R5).

Run: ``python -m pytest -m gui --qt-desktop ...`` (CLAUDE.md). Hotkeys used
here are Ctrl+Alt+Shift+F2x combinations that nothing else uses.

Pinned here:
- ``NativeHotkeys.register / unregister`` follow Win32: 0 on success, else
  the error code (1409 when the combination is taken).
- A registered combination pressed anywhere emits ``activated(id)`` on the
  GUI thread; WM_HOTKEY posted to another window is not ours and emits nothing.
- Together with ``snapocr.hotkeys.register_all``: a taken combination is
  reported as 1409 and the others still fire.
- After ``unregister_all`` and ``close()``, anyone can register the same
  combinations again (F5-5).
"""

import threading

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from snapocr.commands import Command
from snapocr.gui.platform.hotkeys import NativeHotkeys
from snapocr.hotkeys import MOD_NOREPEAT, hotkey_id, parse_hotkey, register_all, unregister_all
from support.win_input import ForeignHotkeyOwner, post_hotkey_message, press_combo, register_raw, unregister_raw

pytestmark = pytest.mark.gui

F24 = parse_hotkey("Ctrl+Alt+Shift+F24")
F23 = parse_hotkey("Ctrl+Alt+Shift+F23")
F22 = parse_hotkey("Ctrl+Alt+Shift+F22")
MAIN = threading.main_thread().ident


@pytest.fixture
def native(qapp):
    hk = NativeHotkeys()
    yield hk
    hk.close()


def test_register_and_activate(qtbot, native):
    seen = []
    native.activated.connect(lambda i: seen.append((i, threading.get_ident())))
    assert native.register(41, F24.mods | MOD_NOREPEAT, F24.vk) == 0
    try:
        with qtbot.waitSignal(native.activated, timeout=2000) as blocker:
            press_combo(F24.mods, F24.vk)
        assert blocker.args == [41]
        assert seen == [(41, MAIN)]
    finally:
        assert native.unregister(41) == 0


def test_taken_combination_reports_1409(native):
    with ForeignHotkeyOwner(F24.mods, F24.vk):
        assert native.register(42, F24.mods | MOD_NOREPEAT, F24.vk) == 1409


def test_unregister_unknown_id_reports_error(native):
    assert native.unregister(4242) == 1419  # ERROR_HOTKEY_NOT_REGISTERED


def test_hotkey_message_for_another_window_is_ignored(qtbot, native):
    other = QWidget()
    other.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
    seen = []
    native.activated.connect(seen.append)
    assert post_hotkey_message(int(other.winId()), 43)
    qtbot.wait(200)
    assert seen == []
    other.deleteLater()


def test_message_for_our_window_is_delivered(qtbot, native):
    with qtbot.waitSignal(native.activated, timeout=2000) as blocker:
        assert post_hotkey_message(native.hwnd, 44)
    assert blocker.args == [44]


def test_register_all_with_one_taken_combination(qtbot, native):
    bindings = {Command.CAPTURE: F24, Command.OCR: F23, Command.TRANSLATE: F22}
    with ForeignHotkeyOwner(F23.mods, F23.vk):
        report = register_all(bindings, native.register)
        try:
            assert [(f.command, f.error_code) for f in report.failed] == [(Command.OCR, 1409)]
            assert set(report.registered.values()) == {Command.CAPTURE, Command.TRANSLATE}
            for hk, command in ((F24, Command.CAPTURE), (F22, Command.TRANSLATE)):
                with qtbot.waitSignal(native.activated, timeout=2000) as blocker:
                    press_combo(hk.mods, hk.vk)
                assert blocker.args == [hotkey_id(command)]
        finally:
            released = unregister_all(report, native.unregister)
    assert sorted(released) == sorted(report.registered)


def test_after_shutdown_the_combinations_are_free(qapp):
    native = NativeHotkeys()
    report = register_all({Command.CAPTURE: F24, Command.OCR: F23}, native.register)
    assert report.failed == []
    unregister_all(report, native.unregister)
    native.close()
    for hk in (F24, F23):
        assert register_raw(hk.mods, hk.vk)
        assert unregister_raw()


def test_close_is_idempotent(qapp):
    native = NativeHotkeys()
    native.close()
    native.close()
