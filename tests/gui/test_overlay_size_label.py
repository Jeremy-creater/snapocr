"""M5 WI-6: the selection size label on the overlay (PRD F18-6; M5 plan D8).

Pinned here:
- ``size_label`` is ``(text, QRect)`` in the overlay's logical coordinates
  while there is a selection being drawn or adjusted, ``None`` before the
  first press and after the overlay finished (confirm, cancel, save, pin).
- The text is the selection's physical size (``size_text``); it follows the
  drag. The rect is placed by ``label_place`` (gap 4) and holds the text.
- Every capture action shows it (annotation on or off).
- It is painted: a dark backdrop in the overlay's picture.
"""

import pytest
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QImage

from snapocr.geometry import Rect, ScreenInfo
from snapocr.gui.overlay import SelectionOverlay
from support import qt_input as qi

pytestmark = pytest.mark.usefixtures("qapp")

BIG = ScreenInfo("A", Rect(0, 0, 800, 600), 1.0, Rect(0, 0, 800, 600))
SCALED = ScreenInfo("B", Rect(0, 0, 400, 300), 1.5, Rect(0, 0, 600, 450))


def frozen(screen) -> QImage:
    image = QImage(screen.physical.w, screen.physical.h, QImage.Format.Format_RGB32)
    image.fill(QColor(200, 200, 200))
    return image


def make(qtbot, screen=BIG, annotate=False) -> SelectionOverlay:
    o = SelectionOverlay(frozen(screen), screen, annotate=annotate)
    qtbot.addWidget(o)
    return o


def test_no_label_before_the_first_press(qtbot):
    assert make(qtbot).size_label is None


def test_the_label_follows_the_drag(qtbot):
    o = make(qtbot)
    qi.press(o, 100, 100)
    qi.move(o, 300, 250)
    assert o.size_label[0] == "200 × 150"
    qi.move(o, 400, 300)
    assert o.size_label[0] == "300 × 200"
    qi.release(o, 400, 300)
    assert o.size_label[0] == "300 × 200"


def test_physical_size_on_a_scaled_screen(qtbot):
    o = make(qtbot, SCALED)
    qi.drag(o, 100, 100, 200, 150)
    assert o.size_label[0] == "150 × 75"


def test_placed_above_the_selection(qtbot):
    o = make(qtbot)
    qi.drag(o, 100, 100, 300, 250)
    text, rect = o.size_label
    assert rect.left() == 100
    assert rect.top() + rect.height() + 4 == 100
    assert rect.width() > o.fontMetrics().horizontalAdvance("200") and rect.height() >= 12


def test_inside_at_the_top_of_the_screen(qtbot):
    o = make(qtbot)
    qi.drag(o, 100, 5, 300, 250)
    _, rect = o.size_label
    assert (rect.left(), rect.top()) == (100, 9)


def test_kept_on_screen_at_the_right_edge(qtbot):
    o = make(qtbot)
    qi.drag(o, 790, 100, 799, 200)
    _, rect = o.size_label
    assert rect.left() + rect.width() <= 800


def test_moving_the_selection_moves_the_label(qtbot):
    o = make(qtbot)
    qi.drag(o, 100, 100, 300, 250)
    qi.drag(o, 200, 200, 250, 260)  # inside: move by (50, 60)
    text, rect = o.size_label
    assert text == "200 × 150"
    assert rect.left() == 150


@pytest.mark.parametrize("end", ["enter", "esc"])
def test_gone_after_the_overlay_finished(qtbot, end):
    o = make(qtbot)
    qi.drag(o, 100, 100, 300, 250)
    qi.key(o, Qt.Key.Key_Return if end == "enter" else Qt.Key.Key_Escape)
    assert o.size_label is None


def test_capture_overlays_show_it_too_and_pin_ends_it(qtbot):
    o = make(qtbot, annotate=True)
    qi.drag(o, 100, 100, 300, 250)
    assert o.size_label[0] == "200 × 150"
    o.toolbar.pin_requested.emit()
    assert o.size_label is None


def test_the_label_is_painted(qtbot):
    o = make(qtbot)
    qi.drag(o, 100, 100, 300, 250)
    _, rect = o.size_label
    image = o.grab().toImage()
    backdrop = image.pixelColor(rect.left() + 2, rect.top() + rect.height() // 2)
    dimmed = image.pixelColor(rect.left() + 2, rect.top() - 6)  # outside the label, still dimmed frame
    assert backdrop.lightness() < 60
    assert dimmed.lightness() > 90
