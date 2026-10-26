"""FIX-4: overlays opened by the hotkey take the keyboard although another program is in front (gui lane).

WI-22 saw WI-20's overlay test lose Esc to an editor window in the
foreground. That test opened the overlays without any hotkey, so the process
had no right to take the foreground. On the real path the hotkey grants that
right: this test puts another program in front, presses snapocr's capture
hotkey, and expects an injected Esc to cancel the session. It passed from the
start, so no foreground code was added (plan, FIX-4).
"""

import ctypes
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

import pytest

from snapocr.gui.platform.launch import start
from snapocr.hotkeys import parse_hotkey
from support.win_input import press_combo

pytestmark = pytest.mark.gui

TESTS = Path(__file__).resolve().parents[1]
VK_ESCAPE = 0x1B
_user32 = ctypes.WinDLL("user32")
_user32.GetForegroundWindow.restype = wintypes.HWND


def foreground() -> int:
    return _user32.GetForegroundWindow() or 0


@pytest.fixture
def other_program_in_front():
    proc = subprocess.Popen([sys.executable, str(TESTS / "support" / "foreground_holder.py")],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        hwnd = int(proc.stdout.readline())
        assert foreground() == hwnd, "the helper could not take the foreground"
        yield hwnd
    finally:
        proc.communicate("\n", timeout=10)


def test_esc_cancels_overlays_opened_while_another_program_is_in_front(qtbot, qapp, tmp_path, other_program_in_front):
    path = tmp_path / "config.local.toml"
    path.write_text('[hotkeys]\ncapture = "Ctrl+Alt+Shift+F21"\n', encoding="utf-8")
    app = start(["snapocr", "--config", str(path)])
    try:
        hk = parse_hotkey("Ctrl+Alt+Shift+F21")
        press_combo(hk.mods, hk.vk)
        qtbot.waitUntil(lambda: len(app.controller.overlays) >= 1, timeout=3000)
        overlays = app.controller.overlays
        qtbot.waitUntil(lambda: foreground() in {int(o.winId()) for o in overlays}, timeout=2000)
        time.sleep(0.1)
        press_combo(0, VK_ESCAPE)
        qtbot.waitUntil(lambda: app.controller.overlays == (), timeout=2000)
    finally:
        app.shutdown()
