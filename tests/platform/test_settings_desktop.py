"""M3 WI-7: the settings window on the real desktop (gui lane; PRD F11-2, F11-3; plan D5, D6).

Pinned here:
- While the settings window is open, pressing one of snapocr's own hotkeys
  is recorded by the focused field (the hotkeys are released, plan D5); it
  neither opens overlays nor toggles the last-results window.
- Real key events carry the Windows virtual-key code: Ctrl+Alt+Shift+1 is
  recorded as "1", not as the shifted character (plan D6).
- Saving registers the new combination with Windows at once and releases
  the old one; the file holds the new values.

Start at login is left unchecked as loaded, so the real Run key is only read.
"""

import ctypes
import time
from ctypes import wintypes

import pytest

from snapocr.commands import Command
from snapocr.config.files import load_config_file
from snapocr.config.settings import settings_of
from snapocr.gui.platform.launch import start
from snapocr.hotkeys import parse_hotkey
from support.win_input import press_combo

pytestmark = pytest.mark.gui

KEYS = {
    "capture": "Ctrl+Alt+Shift+F21",
    "ocr": "Ctrl+Alt+Shift+F19",
    "translate": "Ctrl+Alt+Shift+F20",
    "last_result": "Ctrl+Alt+Shift+F22",
    "code_ocr": "Ctrl+Alt+Shift+F17",  # M3 WI-14: never the user's Alt+5
    "table_ocr": "Ctrl+Alt+Shift+F18",  # M4 WI-15: never the user's Alt+6
}
VK_ESCAPE = 0x1B
_user32 = ctypes.WinDLL("user32")
_user32.GetForegroundWindow.restype = wintypes.HWND


def foreground() -> int:
    return _user32.GetForegroundWindow() or 0


def press(text: str) -> None:
    hk = parse_hotkey(text)
    press_combo(hk.mods, hk.vk)


def test_own_hotkeys_are_recorded_and_saved_ones_work(qtbot, qapp, tmp_path):
    path = tmp_path / "config.local.toml"
    path.write_text("[hotkeys]\n" + "".join(f'{k} = "{v}"\n' for k, v in KEYS.items()), encoding="utf-8")
    app = start(["snapocr", "--config", str(path)])
    try:
        c = app.controller
        # A hotkey gives this process the right to bring its windows to the front (FIX-4).
        press(KEYS["last_result"])
        qtbot.waitUntil(c.history_window.isVisible, timeout=3000)
        c.run(Command.SETTINGS)
        window = c.settings_window
        qtbot.waitUntil(lambda: foreground() == int(window.winId()), timeout=3000)
        capture, ocr = window.hotkey_edits[Command.CAPTURE], window.hotkey_edits[Command.OCR]
        capture.setFocus()
        qtbot.waitUntil(capture.hasFocus, timeout=2000)

        c.history_window.hide()
        press(KEYS["last_result"])  # snapocr's own, paused while the window is open
        qtbot.waitUntil(lambda: capture.text() == KEYS["last_result"], timeout=2000)
        assert not c.history_window.isVisible()
        press(KEYS["capture"])
        qtbot.waitUntil(lambda: capture.text() == KEYS["capture"], timeout=2000)
        assert c.overlays == ()

        press("Ctrl+Alt+Shift+F18")
        qtbot.waitUntil(lambda: capture.text() == "Ctrl+Alt+Shift+F18", timeout=2000)
        ocr.setFocus()
        qtbot.waitUntil(ocr.hasFocus, timeout=2000)
        press("Ctrl+Alt+Shift+1")
        qtbot.waitUntil(lambda: ocr.text() == "Ctrl+Alt+Shift+1", timeout=2000)

        autostart_before = window.autostart_box.isChecked()
        window.save_button.click()
        assert not window.problems_label.isVisible(), window.problems_label.text()
        assert not window.isVisible()
        assert window.autostart_box.isChecked() == autostart_before

        s = settings_of(load_config_file(path).config)
        assert (s.hotkeys[Command.CAPTURE], s.hotkeys[Command.OCR]) == (
            parse_hotkey("Ctrl+Alt+Shift+F18"), parse_hotkey("Ctrl+Alt+Shift+1"))

        press(KEYS["capture"])  # the old combination is released
        time.sleep(0.3)
        qapp.processEvents()
        assert c.overlays == ()
        press("Ctrl+Alt+Shift+F18")
        qtbot.waitUntil(lambda: len(c.overlays) >= 1, timeout=3000)
        overlays = c.overlays
        qtbot.waitUntil(lambda: foreground() in {int(o.winId()) for o in overlays}, timeout=2000)
        time.sleep(0.1)
        press_combo(0, VK_ESCAPE)
        qtbot.waitUntil(lambda: c.overlays == (), timeout=2000)
    finally:
        app.shutdown()
