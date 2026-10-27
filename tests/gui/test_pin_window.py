"""M4 WI-7: pinned screenshot window (PRD F15-2, F15-4; plan D14).

Pinned here:
- ``PinWindow(image, geometry)``: frameless, stays on top, a tool window;
  geometry is ``geometry`` (global logical px); zoom starts at 100; it paints
  the image scaled to the whole window plus a 1 px border.
- Left drag moves the window by the mouse movement.
- The wheel zooms by one step per notch (``zoom_percent``) about the mouse
  point (``zoom_rect`` with the 100% size = ``geometry``'s size).
- Double click or Esc closes it; ``closed`` is emitted once.
- ``menu`` (right click): "复制图片" puts the image on the clipboard as F7-1;
  "关闭" closes the window.
"""

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QContextMenuEvent, QGuiApplication, QImage, QWheelEvent
from PySide6.QtWidgets import QApplication

from snapocr.annotate import zoom_rect
from snapocr.geometry import Rect
from snapocr.gui.imageops import decode_png
from snapocr.gui.pin_window import PinWindow
from support import qt_input as qi
from support.qimages import gradient, pixels

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def make(qtbot):
    def factory(image=None, geometry=Rect(300, 200, 120, 80)):
        window = PinWindow(image if image is not None else gradient(120, 80), geometry)
        qtbot.addWidget(window)
        closed = []
        window.closed.connect(lambda: closed.append(True))
        return window, closed

    return factory


def geo(window) -> Rect:
    g = window.geometry()
    return Rect(g.x(), g.y(), g.width(), g.height())


def wheel(window, x, y, notches):
    pos = QPointF(x, y)
    event = QWheelEvent(
        pos,
        window.mapToGlobal(pos),
        QPoint(0, 0),
        QPoint(0, 120 * notches),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(window, event)


def action(window, text):
    found = [a for a in window.menu.actions() if a.text() == text]
    assert found, text
    return found[0]


def test_window_flags_and_geometry(make):
    window, _ = make()
    flags = window.windowFlags()
    for flag in (Qt.WindowType.FramelessWindowHint, Qt.WindowType.WindowStaysOnTopHint, Qt.WindowType.Tool):
        assert flags & flag, flag
    assert geo(window) == Rect(300, 200, 120, 80)
    assert window.zoom == 100


def test_paints_the_image_with_a_border(make):
    image = gradient(120, 80)
    window, _ = make(image)
    shot = window.grab().toImage()
    assert (shot.width(), shot.height()) == (120, 80)
    assert shot.pixelColor(60, 40) == image.pixelColor(60, 40)
    assert shot.pixelColor(30, 20) == image.pixelColor(30, 20)
    for x, y in [(0, 40), (119, 40), (60, 0), (60, 79)]:
        assert shot.pixelColor(x, y) != image.pixelColor(x, y), (x, y)


def test_left_drag_moves_the_window(make):
    window, _ = make()
    qi.press(window, 10, 10)
    qi.move(window, 60, 30)
    qi.release(window, 60, 30)
    assert geo(window) == Rect(350, 220, 120, 80)


def test_right_press_does_not_move(make):
    window, _ = make()
    qi.press(window, 10, 10, qi.RIGHT)
    qi.move(window, 60, 30, qi.RIGHT)
    assert geo(window) == Rect(300, 200, 120, 80)


def test_wheel_zooms_about_the_mouse(make):
    window, _ = make()
    wheel(window, 60, 40, 1)
    assert window.zoom == 110
    assert geo(window) == zoom_rect(Rect(300, 200, 120, 80), (360, 240), (120, 80), 110)
    wheel(window, 0, 0, -3)
    assert window.zoom == 80


def test_zoom_stops_at_the_limits(make):
    window, _ = make()
    wheel(window, 0, 0, -20)
    assert window.zoom == 10 and geo(window).w == 12
    before = geo(window)
    wheel(window, 0, 0, -1)
    assert window.zoom == 10 and geo(window) == before


def test_zoomed_window_paints_the_whole_image(make):
    image = QImage(120, 80, QImage.Format.Format_RGB32)
    image.fill(QColor("#1e88e5"))
    window, _ = make(image)
    wheel(window, 0, 0, 10)  # 200%
    shot = window.grab().toImage()
    assert (shot.width(), shot.height()) == (240, 160)
    assert shot.pixelColor(200, 140) == QColor("#1e88e5")


@pytest.mark.parametrize("how", ["double", "esc", "menu"])
def test_closing(make, how):
    window, closed = make()
    window.show()
    if how == "double":
        qi.double_click(window, 20, 20)
    elif how == "esc":
        qi.key(window, Qt.Key.Key_Escape)
    else:
        action(window, "关闭").trigger()
    assert not window.isVisible()
    assert closed == [True]


def test_copy_from_the_menu(make):
    image = gradient(120, 80)
    window, _ = make(image)
    cb = QGuiApplication.clipboard()
    cb.setText("sentinel")
    try:
        action(window, "复制图片").trigger()
        mime = cb.mimeData()
        assert mime.hasImage()
        assert pixels(decode_png(bytes(mime.data("image/png")))) == pixels(image)
    finally:
        cb.clear()


def test_closed_is_emitted_once(make):
    window, closed = make()
    window.show()
    window.close()
    window.close()
    assert closed == [True]


def test_right_click_opens_the_menu(make):
    window, _ = make()
    window.show()
    QApplication.sendEvent(window, QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(10, 10), window.mapToGlobal(QPoint(10, 10))))
    assert window.menu.isVisible()
    window.menu.hide()


def test_keeps_the_image(make):
    image = gradient(120, 80)
    window, _ = make(image)
    assert window.image is image


def test_other_buttons_and_keys_are_ignored(make):
    window, closed = make()
    window.show()
    qi.press(window, 10, 10)
    qi.release(window, 10, 10, qi.RIGHT)  # the left drag goes on
    qi.move(window, 20, 10)
    assert geo(window).x == 310
    qi.release(window, 20, 10)
    qi.key(window, Qt.Key.Key_A)
    assert window.isVisible() and closed == []
