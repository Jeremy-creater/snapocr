"""M4 WI-11: picking, moving and deleting marks in the overlay (PRD F14-8).

Pinned here:
- With marks and no tool picked, a left press picks the topmost mark under
  it (``hit_mark`` with the handle tolerance); ``picked`` is its index, or
  ``None`` after a press on nothing. A picked mark gets a dashed outline.
- Dragging a picked mark moves it by the drag (physical px), shown while
  dragging; it is one undo step. A press-release without movement changes
  nothing.
- Delete removes the picked mark (one undo step) and clears ``picked``.
- Picking a tool or undoing clears ``picked``.
"""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QToolButton

from snapocr.annotate import PALETTE, Mark, Tool, moved
from snapocr.geometry import Rect, ScreenInfo
from snapocr.gui.overlay import SelectionOverlay
from support import qt_input as qi

pytestmark = pytest.mark.usefixtures("qapp")

BIG = ScreenInfo("A", Rect(0, 0, 800, 600), 1.0, Rect(0, 0, 800, 600))
HI = ScreenInfo("B", Rect(800, 0, 400, 300), 2.0, Rect(1600, 0, 800, 600))
GREY = QColor(200, 200, 200)
FIRST = Mark(Tool.RECT, ((100, 100), (200, 180)), PALETTE[0], 4)
SECOND = Mark(Tool.RECT, ((150, 150), (300, 250)), PALETTE[0], 4)


def tb(overlay, name) -> QToolButton:
    found = overlay.toolbar.findChild(QToolButton, name)
    assert found is not None, name
    return found


@pytest.fixture
def two_marks(qtbot):
    image = QImage(800, 600, QImage.Format.Format_RGB32)
    image.fill(GREY)
    overlay = SelectionOverlay(image, BIG, annotate=True)
    qtbot.addWidget(overlay)
    qi.drag(overlay, 50, 50, 400, 350)
    tb(overlay, "tool-rect").click()
    qi.drag(overlay, 100, 100, 200, 180)
    qi.drag(overlay, 150, 150, 300, 250)
    tb(overlay, "tool-rect").click()  # no tool
    assert overlay.marks == (FIRST, SECOND)
    return overlay


def click(overlay, x, y):
    qi.press(overlay, x, y)
    qi.release(overlay, x, y)


def test_press_picks_the_topmost_mark(two_marks):
    assert two_marks.picked is None
    click(two_marks, 170, 170)
    assert two_marks.picked == 1
    click(two_marks, 110, 110)
    assert two_marks.picked == 0
    click(two_marks, 350, 300)
    assert two_marks.picked is None
    assert two_marks.marks == (FIRST, SECOND)
    assert two_marks.selection == Rect(50, 50, 350, 300)


def test_picked_mark_has_an_outline(two_marks):
    before = two_marks.grab().toImage()
    click(two_marks, 110, 110)
    after = two_marks.grab().toImage()
    changed = [(x, y) for y in range(85, 200) for x in range(85, 220) if before.pixel(x, y) != after.pixel(x, y)]
    assert changed
    assert all(not (106 <= x <= 194 and 106 <= y <= 174) for x, y in changed)  # only around the box


def test_drag_moves_the_picked_mark(two_marks):
    qi.press(two_marks, 110, 110)
    qi.move(two_marks, 130, 100)
    assert two_marks.marks == (FIRST, SECOND)  # not committed yet
    shot = two_marks.grab().toImage()
    assert shot.pixelColor(120, 140) == QColor(PALETTE[0])  # the left edge, moved right by 20
    qi.release(two_marks, 140, 95)
    assert two_marks.marks == (moved(FIRST, 30, -15), SECOND)
    assert two_marks.picked == 0
    tb(two_marks, "undo").click()
    assert two_marks.marks == (FIRST, SECOND)
    assert two_marks.picked is None


def test_click_without_moving_changes_nothing(two_marks):
    click(two_marks, 110, 110)
    tb(two_marks, "undo").click()
    assert two_marks.marks == (FIRST,)  # the undo took back the second rectangle, not a move


def test_delete_removes_the_picked_mark(two_marks):
    click(two_marks, 170, 170)
    qi.key(two_marks, Qt.Key.Key_Delete)
    assert two_marks.marks == (FIRST,) and two_marks.picked is None
    qi.key(two_marks, Qt.Key.Key_Delete)
    assert two_marks.marks == (FIRST,)
    tb(two_marks, "undo").click()
    assert two_marks.marks == (FIRST, SECOND)


def test_delete_with_nothing_picked_does_nothing(two_marks):
    qi.key(two_marks, Qt.Key.Key_Delete)
    assert two_marks.marks == (FIRST, SECOND)


def test_picking_a_tool_clears_the_pick(two_marks):
    click(two_marks, 110, 110)
    tb(two_marks, "tool-ellipse").click()
    assert two_marks.picked is None
    qi.drag(two_marks, 120, 120, 160, 160)  # draws, does not move
    assert two_marks.marks[:2] == (FIRST, SECOND) and len(two_marks.marks) == 3


def test_move_on_a_scaled_screen_is_physical(qtbot):
    image = QImage(800, 600, QImage.Format.Format_RGB32)
    image.fill(GREY)
    overlay = SelectionOverlay(image, HI, annotate=True)
    qtbot.addWidget(overlay)
    qi.drag(overlay, 20, 20, 300, 250)
    tb(overlay, "tool-arrow").click()
    qi.drag(overlay, 50, 50, 150, 100)
    tb(overlay, "tool-arrow").click()
    first = overlay.marks[0]
    qi.press(overlay, 100, 75)
    qi.move(overlay, 110, 80)
    qi.release(overlay, 110, 80)
    assert overlay.marks == (moved(first, 20, 10),)
