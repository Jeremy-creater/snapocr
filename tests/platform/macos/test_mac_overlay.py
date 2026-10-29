"""M9 WI-18: overlays above the menu bar and the Dock, taking the keys (gui-mac lane; PRD F23-4, plan D16).

Pinned here:
- ``prepare_overlay`` puts the overlay's NSWindow at ``NSStatusWindowLevel``
  (above the menu bar, 24, and the Dock, 20), on every Space and over
  full-screen apps, never hidden on deactivation, framed on the whole screen.
- While the overlays are up, a capture of the menu bar shows the overlay's
  dimmed picture, not the menu bar.
- With another app in front, Esc reaches the overlay and cancels the session.

Full-screen Spaces are checked by hand (WI-25).
"""

import ctypes
import subprocess
import time

import pytest
from PySide6.QtCore import Qt

from snapocr.geometry import crop_box
from snapocr.gui.imageops import crop
from snapocr.gui.overlay import OverlaySession, SelectionOverlay
from snapocr.gui.platform.mac import _cocoa as c
from snapocr.gui.platform.mac.capture import MacCapture
from snapocr.gui.platform.mac.overlay import prepare_overlay
from support.mac_input import kVK_Escape, press_key
from support.mac_permissions import require_screen_recording

pytestmark = pytest.mark.gui

OTHER_APP = "Calculator"


@pytest.fixture
def session(qtbot, qapp):
    require_screen_recording()
    cap = MacCapture().capture()
    overlays = [SelectionOverlay(crop(cap.image, crop_box(s.physical, cap.origin)), s) for s in cap.screens]
    session = OverlaySession(overlays, prepare=prepare_overlay)
    results = []
    session.result.connect(results.append)
    yield session, overlays, cap, results
    for o in overlays:
        o.close()
        o.deleteLater()


def ns_window(widget):
    return c.send(ctypes.c_void_p(int(widget.winId())), "window")


def test_overlay_windows_sit_above_the_menu_bar_on_every_space(qtbot, session):
    session_, overlays, cap, _ = session
    session_.start()
    for o, s in zip(overlays, cap.screens):
        qtbot.waitExposed(o)
        window = ns_window(o)
        assert c.send(window, "level", restype=ctypes.c_long) >= c.NSStatusWindowLevel
        behavior = c.send(window, "collectionBehavior", restype=ctypes.c_ulong)
        wanted = c.NSWindowCollectionBehaviorCanJoinAllSpaces | c.NSWindowCollectionBehaviorFullScreenAuxiliary
        assert behavior & wanted == wanted
        assert c.send(window, "hidesOnDeactivate", restype=ctypes.c_bool) is False
        f = c.send(window, "frame", restype=c.CGRect)
        assert (f.size.width, f.size.height) == (s.logical.w, s.logical.h)
        assert o.geometry().topLeft().toTuple() == (s.logical.x, s.logical.y)


def test_a_capture_of_the_menu_bar_shows_the_overlay(qtbot, session):
    session_, overlays, cap, _ = session
    session_.start()
    for o in overlays:
        qtbot.waitExposed(o)
    qtbot.wait(300)
    shown = MacCapture().capture()
    for o, s in zip(overlays, cap.screens):
        drawn = o.grab().toImage()  # what the overlay paints, at the screen's dpr
        for x in (s.physical.w // 4, s.physical.w * 3 // 4):  # either side of a notch
            y = round(6 * s.dpr)  # inside the menu bar
            want, got = drawn.pixelColor(x, y), shown.image.pixelColor(s.physical.x + x, y)
            before = cap.image.pixelColor(s.physical.x + x, y)
            diff = max(abs(want.red() - got.red()), abs(want.green() - got.green()), abs(want.blue() - got.blue()))
            assert diff <= 12, f"{s.name} at ({x}, {y}): overlay {want.getRgb()}, screen {got.getRgb()}"
            assert got.lightness() < before.lightness() or before.lightness() < 40, "the menu bar is not dimmed"


@pytest.fixture
def other_app_in_front():
    was_running = subprocess.run(["pgrep", "-x", OTHER_APP], capture_output=True).returncode == 0
    subprocess.run(["open", "-a", OTHER_APP], check=True)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and _frontmost() != OTHER_APP:
        time.sleep(0.1)
    assert _frontmost() == OTHER_APP, f"{OTHER_APP} did not come to the front"
    yield
    if not was_running:
        subprocess.run(["osascript", "-e", f'tell application "{OTHER_APP}" to quit'], check=False)


def _frontmost() -> str:
    out = subprocess.run(
        ["osascript", "-e", 'tell application "System Events" to get name of first process whose frontmost is true'],
        capture_output=True, text=True,
    )
    return out.stdout.strip()


def test_esc_reaches_the_overlay_while_another_app_is_in_front(qtbot, session, other_app_in_front):
    session_, overlays, _, results = session
    session_.start()
    for o in overlays:
        qtbot.waitExposed(o)
    qtbot.waitUntil(lambda: overlays[0].isActiveWindow(), timeout=2000)
    press_key(kVK_Escape)
    qtbot.waitUntil(lambda: results == [None], timeout=2000)
    assert not any(o.isVisible() for o in overlays)
