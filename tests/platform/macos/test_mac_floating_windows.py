"""M9: the pin and the translation window stay up when another app comes forward (gui-mac lane; PRD F15, F23-9).

``Qt.Tool`` makes an NSPanel on a Mac, and a panel hides whenever its app is
not the active one (measured in WI-17). A pinned screenshot is meant to be
looked at while working in another app, so it must stay.

What is on screen is read from a real capture: after the switch AppKit still
reports ``isVisible`` YES for the hidden panel (measured 2026-10-30), so only
the pixels tell. The window's centre on screen must match what it paints.
"""

import ctypes
import subprocess
import time

import pytest
from PySide6.QtGui import QColor, QImage

from snapocr.geometry import Rect
from snapocr.gui.pin_window import PinWindow
from snapocr.gui.platform.mac import _cocoa as c
from snapocr.gui.platform.mac.capture import MacCapture
from snapocr.gui.popup import TranslationPopup
from support.mac_permissions import require_screen_recording

pytestmark = pytest.mark.gui

OTHER_APP = "Calculator"


def frontmost() -> str:
    out = subprocess.run(
        ["osascript", "-e", 'tell application "System Events" to get name of first process whose frontmost is true'],
        capture_output=True, text=True,
    )
    return out.stdout.strip()


@pytest.fixture
def other_app():
    was_running = subprocess.run(["pgrep", "-x", OTHER_APP], capture_output=True).returncode == 0

    def bring_forward():
        subprocess.run(["open", "-a", OTHER_APP], check=True)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and frontmost() != OTHER_APP:
            time.sleep(0.1)
        assert frontmost() == OTHER_APP, f"{OTHER_APP} did not come to the front"

    yield bring_forward
    if not was_running:
        subprocess.run(["osascript", "-e", f'tell application "{OTHER_APP}" to quit'], check=False)


def on_screen(widget) -> bool:
    """Whether the screen shows ``widget``'s own pixels at its centre."""
    centre = widget.geometry().center()
    cap = MacCapture().capture()
    (s,) = [s for s in cap.screens if s.logical.x <= centre.x() < s.logical.x + s.logical.w
            and s.logical.y <= centre.y() < s.logical.y + s.logical.h]
    want = widget.grab().toImage().pixelColor(round(widget.width() / 2 * s.dpr), round(widget.height() / 2 * s.dpr))
    got = cap.image.pixelColor(s.physical.x + round((centre.x() - s.logical.x) * s.dpr),
                               s.physical.y + round((centre.y() - s.logical.y) * s.dpr))
    return max(abs(want.red() - got.red()), abs(want.green() - got.green()), abs(want.blue() - got.blue())) <= 12


def stays_up(qtbot, widget, bring_forward):
    require_screen_recording()
    qtbot.addWidget(widget)
    widget.show()
    c.send(c.ns_app(), "activateIgnoringOtherApps:", True, argtypes=(ctypes.c_bool,), restype=None)
    qtbot.waitExposed(widget)
    qtbot.wait(300)
    assert on_screen(widget), "not on screen even while snapocr is active"
    bring_forward()
    qtbot.wait(500)
    return on_screen(widget)


def test_a_pin_stays_when_another_app_comes_forward(qtbot, qapp, other_app):
    image = QImage(160, 90, QImage.Format.Format_RGB32)
    image.fill(QColor("teal"))
    assert stays_up(qtbot, PinWindow(image, Rect(200, 200, 160, 90)), other_app)


def test_the_translation_window_stays_when_another_app_comes_forward(qtbot, qapp, other_app):
    popup = TranslationPopup(platform="darwin")
    popup.move(240, 320)
    assert stays_up(qtbot, popup, other_app)
