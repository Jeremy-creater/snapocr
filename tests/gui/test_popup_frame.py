"""M7 WI-4: the frameless translation window: title bar, close button, drag, resize (PRD F20-5; M7 plan D8).

Pinned here (beyond the plan text):
- The window has no system frame and a translucent background (it paints its
  own rounded fill); the title bar is the top ``TITLE_HEIGHT`` pixels.
- Offscreen, ``QWindow.startSystemMove`` / ``startSystemResize`` are refused,
  so the window follows the mouse itself: these tests drive that path with
  real mouse events (global positions, as the window moves under them).
- Pressing on a button in the title bar does not drag. The cursor over an
  edge shows the resize arrow.
- ``place`` on a screen smaller than the minimum still fits the screen.
"""

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from snapocr.actions.outcomes import Done, Translating
from snapocr.geometry import Rect
from snapocr.gui.popup import MIN_SIZE, TITLE_HEIGHT, TranslationPopup
from support import qt_input as qi

LEFT = Qt.MouseButton.LeftButton


@pytest.fixture
def window(qtbot):
    w = TranslationPopup()
    qtbot.addWidget(w)
    w.setGeometry(QRect(200, 150, 420, 260))
    w.show()
    qtbot.waitExposed(w)
    return w


def send(widget, kind, global_pos, button, buttons):
    local = QPointF(widget.mapFromGlobal(global_pos))
    QApplication.sendEvent(widget, QMouseEvent(kind, local, QPointF(global_pos), button, buttons,
                                               Qt.KeyboardModifier.NoModifier))


def drag_global(widget, start_local, delta, steps=3):
    start = widget.mapToGlobal(QPoint(*start_local))
    send(widget, QEvent.Type.MouseButtonPress, start, LEFT, LEFT)
    for i in range(1, steps + 1):
        p = start + QPoint(delta[0] * i // steps, delta[1] * i // steps)
        send(widget, QEvent.Type.MouseMove, p, Qt.MouseButton.NoButton, LEFT)
    send(widget, QEvent.Type.MouseButtonRelease, start + QPoint(*delta), LEFT, Qt.MouseButton.NoButton)


def test_frameless_and_translucent(window):
    assert window.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert window.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert window.title_label.text() == "翻译"
    assert window.title_label.isVisible()
    assert window.close_button.isVisible()
    assert window.close_button.geometry().bottom() < TITLE_HEIGHT


def test_close_button_hides_and_a_late_result_does_not_reshow(qtbot, window):
    window.apply(1, Translating("hi"))
    qtbot.mouseClick(window.close_button, LEFT)
    assert not window.isVisible()
    window.apply(1, Done("hi", "T(hi)"))
    assert not window.isVisible()
    assert window.translation_view.toPlainText() == "T(hi)"


def test_drag_the_title_bar_moves_the_window(window):
    before = window.geometry()
    drag_global(window, (150, TITLE_HEIGHT // 2), (40, 25))
    assert window.geometry() == before.translated(40, 25)


def test_drag_below_the_title_bar_does_not_move(window):
    before = window.geometry()
    drag_global(window, (150, TITLE_HEIGHT + 12), (40, 25))  # the layout margin under the title bar
    assert window.geometry() == before


def test_press_on_the_close_button_does_not_drag(qtbot, window):
    before = window.geometry()
    centre = window.close_button.rect().center()
    qi.press(window.close_button, centre.x(), centre.y())
    qi.move(window.close_button, centre.x() + 40, centre.y() + 25)
    assert window.geometry() == before


def test_drag_the_bottom_right_corner_resizes(window):
    before = window.geometry()
    drag_global(window, (before.width() - 2, before.height() - 2), (30, 20))
    assert window.geometry() == QRect(before.x(), before.y(), before.width() + 30, before.height() + 20)


def test_drag_the_left_edge_keeps_the_right_edge(window):
    before = window.geometry()
    drag_global(window, (1, 130), (-50, 10))
    assert window.geometry() == QRect(before.x() - 50, before.y(), before.width() + 50, before.height())


def test_resize_stops_at_the_minimum(window):
    before = window.geometry()
    drag_global(window, (before.width() - 2, before.height() - 2), (-400, -400))
    assert (window.width(), window.height()) == MIN_SIZE == (320, 220)
    assert window.pos() == before.topLeft()


@pytest.mark.parametrize(
    ("where", "shape"),
    [
        ("right", Qt.CursorShape.SizeHorCursor),
        ("bottom", Qt.CursorShape.SizeVerCursor),
        ("corner", Qt.CursorShape.SizeFDiagCursor),
        ("inside", Qt.CursorShape.ArrowCursor),
    ],
)
def test_cursor_over_the_edges(window, where, shape):
    w, h = window.width(), window.height()
    x, y = {"right": (w - 2, 130), "bottom": (200, h - 2), "corner": (w - 2, h - 2), "inside": (200, 10)}[where]
    qi.move(window, x, y, buttons=Qt.MouseButton.NoButton)
    assert window.cursor().shape() == shape


def test_place_on_a_screen_smaller_than_the_minimum_still_fits(window):
    window.place(Rect(-1600, 50, 50, 50), Rect(-1707, 0, 300, 200))
    g = window.geometry()
    assert g.width() <= 300 and g.height() <= 200
    window.place(Rect(100, 100, 50, 50), Rect(0, 0, 1920, 1040))
    assert window.minimumWidth() == 320 and window.minimumHeight() == 220


@pytest.mark.parametrize("start", [(150, TITLE_HEIGHT // 2), (418, 258)], ids=["move", "resize"])
def test_a_drag_the_system_takes_is_not_followed_again(window, monkeypatch, start):
    """On the real desktop the system moves or resizes the window; it must not also follow the mouse."""
    taken = []
    monkeypatch.setattr(window, "_start_system_drag", lambda edges: taken.append(edges) or True)
    before = window.geometry()
    drag_global(window, start, (40, 25))
    assert window.geometry() == before
    assert taken == [frozenset() if start[1] < TITLE_HEIGHT else frozenset({"right", "bottom"})]
