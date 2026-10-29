"""M9 WI-17: capture on the real Mac (gui-mac lane; PRD F23-3, F23-4, plan D13 to D15).

Pinned here:
- ``MacCapture().capture()``: every screen grabbed with ``CGDisplayCreateImage``
  and laid side by side (WI-16 ``stack_physical``), RGB32, origin (0, 0); one
  ``ScreenInfo`` per Qt screen, named after the screen and its display id so
  two identical monitors never share a name; work areas by that name.
- F23-4 core: a window of 1-logical-px black and white stripes on each screen is
  found at its physical spot with stripes ``dpr`` pixels wide. That is real
  content, not the wallpaper-only image macOS gives without the permission.
  Black and white survive the display's colour profile; exact colours do not.
- Without the permission: asked once, ``CapturePermissionError``, nothing grabbed.
- Screens that cannot be paired, an unknown display, or a grab of the wrong
  size are ``CaptureError``.

Only one screen here (the built-in display); several screens are covered by the
WI-16 properties and the WI-25 hand check with an external monitor.
"""

import pytest
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter
from PySide6.QtWidgets import QWidget

from snapocr.geometry import Rect
from snapocr.gui.boundaries import CaptureError, CapturePermissionError
from snapocr.gui.platform.mac.capture import MacCapture, cg_displays, grab_display
from support.mac_permissions import require_screen_recording

pytestmark = pytest.mark.gui

STRIPES = (64, 32)  # logical size of the stripe window
OFFSET = (120, 160)  # logical offset from the screen's top-left, clear of the menu bar


@pytest.fixture(autouse=True)
def screen_recording(qapp):
    require_screen_recording()


def test_capture_is_every_screen_side_by_side(qapp):
    cap = MacCapture().capture()
    qt = QGuiApplication.screens()
    assert cap.origin == (0, 0)
    assert cap.image.format() == QImage.Format.Format_RGB32
    assert len(cap.screens) == len(qt)
    x = 0
    for info, qs in zip(cap.screens, qt):
        g, a = qs.geometry(), qs.availableGeometry()
        assert info.logical == Rect(g.x(), g.y(), g.width(), g.height())
        assert info.dpr == qs.devicePixelRatio()
        assert info.physical == Rect(x, 0, round(g.width() * info.dpr), round(g.height() * info.dpr))
        assert info.name.startswith(qs.name() + " #")
        assert cap.work_areas[info.name] == Rect(a.x(), a.y(), a.width(), a.height())
        x += info.physical.w
    assert (cap.image.width(), cap.image.height()) == (x, max(s.physical.h for s in cap.screens))
    assert len({s.name for s in cap.screens}) == len(cap.screens)


class StripeWindow(QWidget):
    """1-logical-px vertical stripes, black first.

    Not ``Qt.Tool``: on a Mac that is an NSPanel, which hides whenever the app
    is not active, so the window was never on screen (measured under pytest).
    """

    def __init__(self):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("white"))
        for x in range(0, self.width(), 2):
            p.fillRect(x, 0, 1, self.height(), QColor("black"))
        p.end()


def _shade(image: QImage, x: int, y: int) -> str:
    c = image.pixelColor(x, y)
    luma = (c.red() + c.green() + c.blue()) / 3
    return "b" if luma < 64 else "w" if luma > 192 else "?"


@pytest.mark.parametrize("index", range(len(QGuiApplication.screens()) if QGuiApplication.instance() else 1))
def test_stripes_are_dpr_pixels_wide_where_the_window_is(qtbot, qapp, index):
    screens = QGuiApplication.screens()
    if index >= len(screens):
        pytest.fail(f"expected at least {index + 1} screens, found {len(screens)}")
    g = screens[index].geometry()
    window = StripeWindow()
    qtbot.addWidget(window)
    window.setGeometry(QRect(g.x() + OFFSET[0], g.y() + OFFSET[1], *STRIPES))
    window.show()
    qtbot.waitExposed(window)
    seen = []

    def stripes_captured():
        cap = MacCapture().capture()  # until the window server has composed the window
        s = cap.screens[index]
        d = round(s.dpr)
        y = s.physical.y + round((OFFSET[1] + STRIPES[1] / 2) * s.dpr)
        x0 = s.physical.x + round(OFFSET[0] * s.dpr)
        row = "".join(_shade(cap.image, x0 + i, y) for i in range(STRIPES[0] * d))
        seen[:] = [f"{s.name} (dpr {s.dpr}): {row}"]
        return row == ("b" * d + "w" * d) * (STRIPES[0] // 2)

    try:
        qtbot.waitUntil(stripes_captured, timeout=3000)
    except qtbot.TimeoutError:
        pytest.fail(f"stripes not found; window {window.geometry()} on {window.screen().name()} visible {window.isVisible()}; last row {seen[0]}")
    finally:
        window.hide()


def test_without_the_permission_it_asks_once_and_grabs_nothing(qapp):
    asked, grabbed = [], []
    capture = MacCapture(
        preflight=lambda: False,
        request=lambda: asked.append(1) or False,
        grab=lambda display: grabbed.append(display),
    )
    with pytest.raises(CapturePermissionError):
        capture.capture()
    assert (asked, grabbed) == ([1], [])


def test_screens_that_cannot_be_paired_are_a_capture_error(qapp):
    with pytest.raises(CaptureError, match="screen count differs") as err:
        MacCapture(displays=lambda: []).capture()
    assert QGuiApplication.screens()[0].name() in str(err.value)


def test_a_grab_of_the_wrong_size_is_a_capture_error(qapp):
    with pytest.raises(CaptureError, match="10x10"):
        MacCapture(grab=lambda display: QImage(10, 10, QImage.Format.Format_RGB32)).capture()


def test_no_display_is_a_capture_error(qapp):
    """kCGNullDirectDisplay. An unknown non-zero id still returns an image (measured), so 0 is the only way in."""
    with pytest.raises(CaptureError, match="CGDisplayCreateImage"):
        grab_display(0)


def test_cg_displays_match_qt_screens(qapp):
    def key(r):
        return (r.x, r.y, r.w, r.h)

    rects = sorted((r for _, r in cg_displays()), key=key)
    qt = sorted((Rect(g.x(), g.y(), g.width(), g.height()) for g in (s.geometry() for s in QGuiApplication.screens())), key=key)
    assert rects == qt
