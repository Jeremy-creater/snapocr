"""M2 WI-20: screens and capture on the real desktop (gui lane; PRD F6-1, F6-2; plan D4, R4).

Pinned here:
- After the QApplication exists the GUI thread is Per-Monitor-V2 aware.
- ``qt_screen_infos()`` pairs every QScreen with its Win32 monitor: the device
  name is looked up at the screen's origin (Qt keeps screen origins in native
  pixels on Windows; ``QScreen.name()`` is the model name), then WI-3
  ``match_screens`` checks the sizes. It returns the ScreenInfos (Qt order)
  and each screen's available geometry (logical) by device name.
- ``grab_physical(rect)`` returns exactly ``rect``'s physical pixels as RGB32;
  an empty rect raises ``CaptureError``.
- ``DesktopCapture().capture()``: the whole virtual desktop, origin at its
  top-left; a screen mismatch becomes ``CaptureError``.
- F6-2 core: a known pattern shown at a known physical spot on each screen is
  captured pixel for pixel (1 px border allowed for antialiasing).
- Real overlays cover each screen and receive Esc.
"""

import pytest
from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter
from PySide6.QtWidgets import QWidget

from snapocr.geometry import Rect, ScreenMismatch, crop_box
from snapocr.gui.boundaries import CaptureError
from snapocr.gui.imageops import crop
from snapocr.gui.overlay import OverlaySession, SelectionOverlay
from snapocr.gui.platform.capture import DesktopCapture, grab_physical, virtual_desktop
from snapocr.gui.platform.screens import enum_monitors, is_per_monitor_v2, qt_screen_infos
from support.win_input import press_combo

pytestmark = pytest.mark.gui

VK_ESCAPE = 0x1B
PATTERN = (240, 120)  # physical px; divisible by 1.25, 1.5 and 2
OFFSET = (600, 300)  # physical offset from the screen's top-left


def test_thread_is_per_monitor_v2(qapp):
    assert is_per_monitor_v2()


def test_every_qt_screen_pairs_with_a_monitor(qapp):
    screens, work = qt_screen_infos()
    monitors = dict(enum_monitors())
    assert len(screens) == len(QGuiApplication.screens()) == len(monitors)
    for info, qs in zip(screens, QGuiApplication.screens()):
        assert info.physical == monitors[info.name]
        g, a = qs.geometry(), qs.availableGeometry()
        assert info.logical == Rect(g.x(), g.y(), g.width(), g.height())
        assert info.dpr == qs.devicePixelRatio()
        assert work[info.name] == Rect(a.x(), a.y(), a.width(), a.height())


def test_screen_mismatch_becomes_capture_error(qapp):
    def broken():
        raise ScreenMismatch("screen names differ")

    with pytest.raises(CaptureError, match="screen names differ"):
        DesktopCapture(screens=broken).capture()


def test_capture_covers_the_virtual_desktop(qapp):
    cap = DesktopCapture().capture()
    v = virtual_desktop()
    assert cap.origin == (v.x, v.y)
    assert (cap.image.width(), cap.image.height()) == (v.w, v.h)
    assert cap.image.format() == QImage.Format.Format_RGB32
    for s in cap.screens:  # every screen lies inside the image
        box = crop_box(s.physical, cap.origin)
        assert box.x >= 0 and box.y >= 0 and box.x + box.w <= v.w and box.y + box.h <= v.h


def test_grab_of_an_empty_rect_raises(qapp):
    with pytest.raises(CaptureError):
        grab_physical(Rect(0, 0, 0, 0))


def pattern_image() -> QImage:
    w, h = PATTERN
    image = QImage(w, h, QImage.Format.Format_RGB32)
    for y in range(h):
        for x in range(w):
            image.setPixelColor(x, y, QColor((x * 5) % 256, (y * 7 + x) % 256, 255 - (x + 2 * y) % 200))
    image.setPixelColor(3, 2, QColor(255, 0, 255))  # asymmetric marker
    return image


class PatternWindow(QWidget):
    def __init__(self, image: QImage, dpr: float):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self._image = QImage(image)
        self._image.setDevicePixelRatio(dpr)

    def paintEvent(self, event):
        p = QPainter(self)
        p.drawImage(QRectF(0, 0, self.width(), self.height()), self._image, QRectF(self._image.rect()))
        p.end()


@pytest.mark.parametrize("index", range(len(QGuiApplication.screens()) if QGuiApplication.instance() else 2))
def test_known_pattern_is_captured_pixel_for_pixel(qtbot, qapp, index):
    screens, _ = qt_screen_infos()
    if index >= len(screens):
        pytest.fail(f"expected at least {index + 1} screens, found {len(screens)}")
    s = screens[index]
    w, h = PATTERN
    ox, oy = OFFSET
    window = PatternWindow(pattern_image(), s.dpr)
    qtbot.addWidget(window)
    window.setGeometry(QRect(round(s.logical.x + ox / s.dpr), round(s.logical.y + oy / s.dpr), round(w / s.dpr), round(h / s.dpr)))
    window.show()
    qtbot.waitExposed(window)
    qtbot.wait(400)  # let DWM compose the window
    cap = DesktopCapture().capture()
    window.hide()
    target = Rect(s.physical.x + ox, s.physical.y + oy, w, h)
    got = crop(cap.image, crop_box(target, cap.origin))
    want = pattern_image()
    mismatches = [
        (x, y) for y in range(1, h - 1) for x in range(1, w - 1) if got.pixel(x, y) != want.pixel(x, y)
    ]
    assert mismatches == [], f"{len(mismatches)} pixels differ on {s.name} (dpr {s.dpr}); first {mismatches[:5]}"


def test_real_overlays_cover_each_screen_and_take_esc(qtbot, qapp):
    cap = DesktopCapture().capture()
    overlays = [SelectionOverlay(crop(cap.image, crop_box(s.physical, cap.origin)), s) for s in cap.screens]
    session = OverlaySession(overlays)
    results = []
    session.result.connect(results.append)
    # As on the real path, receive a hotkey first: that is what lets the process
    # take the foreground from whatever program is in front (FIX-4).
    from snapocr.gui.platform.hotkeys import NativeHotkeys
    from snapocr.hotkeys import parse_hotkey

    grant, trigger = NativeHotkeys(), parse_hotkey("Ctrl+Alt+Shift+F20")
    assert grant.register(77, trigger.mods, trigger.vk) == 0
    with qtbot.waitSignal(grant.activated, timeout=2000):
        press_combo(trigger.mods, trigger.vk)
    grant.unregister(77)
    grant.close()
    try:
        session.start()
        for o, s in zip(overlays, cap.screens):
            qtbot.waitExposed(o)
            assert o.geometry() == QRect(s.logical.x, s.logical.y, s.logical.w, s.logical.h)
        qtbot.wait(300)
        press_combo(0, VK_ESCAPE)
        qtbot.waitUntil(lambda: results == [None], timeout=2000)
    finally:
        for o in overlays:
            o.close()
            o.deleteLater()
