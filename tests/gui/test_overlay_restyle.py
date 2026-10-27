"""M4 WI-18: changing the colour or size of a drawn mark (PRD F14-10; plan D17).

Pinned here:
- With a mark picked, a colour click recolours just that mark and a level
  click resizes just that mark (``with_level``; text re-measured with
  ``fit_text``); the other property stays. Each change is one undo step; a
  click that changes nothing adds no step. The mark stays picked.
- The click still sets the style of later marks.
- With nothing picked, clicks change no mark.
- ``fit_text(mark, size)``: the same text at ``size``, top-left kept, box
  re-measured like ``text_mark``.
"""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QToolButton

from snapocr.annotate import PALETTE, Mark, Style, Tool, scaled
from snapocr.geometry import Rect, ScreenInfo
from snapocr.gui.marks_paint import fit_text, text_mark
from snapocr.gui.overlay import SelectionOverlay
from support import qt_input as qi

pytestmark = pytest.mark.usefixtures("qapp")

BIG = ScreenInfo("A", Rect(0, 0, 800, 600), 1.0, Rect(0, 0, 800, 600))
HI = ScreenInfo("B", Rect(800, 0, 400, 300), 2.0, Rect(1600, 0, 800, 600))
RED_RECT = Mark(Tool.RECT, ((100, 100), (200, 180)), PALETTE[0], 4)
BLUE_RECT = Mark(Tool.RECT, ((250, 250), (350, 330)), PALETTE[4], 4)


def tb(overlay, name) -> QToolButton:
    found = overlay.toolbar.findChild(QToolButton, name)
    assert found is not None, name
    return found


def click(overlay, x, y):
    qi.press(overlay, x, y)
    qi.release(overlay, x, y)


def make(qtbot, screen=BIG):
    image = QImage(screen.physical.w, screen.physical.h, QImage.Format.Format_RGB32)
    image.fill(QColor(200, 200, 200))
    overlay = SelectionOverlay(image, screen, annotate=True)
    qtbot.addWidget(overlay)
    if screen is BIG:
        qi.drag(overlay, 50, 50, 500, 450)
    else:
        qi.drag(overlay, 20, 20, 300, 250)
    return overlay


@pytest.fixture
def two_rects(qtbot):
    overlay = make(qtbot)
    tb(overlay, "tool-rect").click()
    qi.drag(overlay, 100, 100, 200, 180)
    tb(overlay, "color-4").click()
    qi.drag(overlay, 250, 250, 350, 330)
    tb(overlay, "tool-rect").click()  # no tool
    return overlay


def test_fixture(two_rects):
    assert two_rects.marks == (RED_RECT, BLUE_RECT)


def test_colour_click_recolours_the_picked_mark(two_rects):
    click(two_rects, 300, 300)
    tb(two_rects, "color-0").click()  # red; the toolbar was on blue
    assert two_rects.marks == (RED_RECT, Mark(Tool.RECT, BLUE_RECT.points, PALETTE[0], 4))
    assert two_rects.picked == 1
    tb(two_rects, "color-3").click()
    assert two_rects.marks[1].color == PALETTE[3]
    tb(two_rects, "undo").click()
    assert two_rects.marks[1].color == PALETTE[0]
    tb(two_rects, "undo").click()
    assert two_rects.marks == (RED_RECT, BLUE_RECT)


def test_level_click_resizes_only(two_rects):
    click(two_rects, 110, 110)
    tb(two_rects, "level-2").click()
    assert two_rects.marks == (Mark(Tool.RECT, RED_RECT.points, PALETTE[0], 6), BLUE_RECT)
    assert two_rects.picked == 0


def test_click_that_changes_nothing_adds_no_undo_step(two_rects):
    click(two_rects, 110, 110)
    tb(two_rects, "color-0").click()  # already red
    tb(two_rects, "level-1").click()  # already 4 px
    assert two_rects.marks == (RED_RECT, BLUE_RECT)
    tb(two_rects, "undo").click()
    assert two_rects.marks == (RED_RECT,)  # took back the blue rectangle


def test_the_click_also_sets_the_next_style(two_rects):
    click(two_rects, 110, 110)
    tb(two_rects, "color-3").click()
    assert two_rects.toolbar.style == Style(PALETTE[3], 1)


def test_nothing_picked_changes_no_mark(two_rects):
    tb(two_rects, "color-5").click()
    tb(two_rects, "level-0").click()
    assert two_rects.marks == (RED_RECT, BLUE_RECT)


def test_level_on_a_scaled_screen_is_physical(qtbot):
    overlay = make(qtbot, HI)
    tb(overlay, "tool-number").click()
    click(overlay, 100, 100)
    tb(overlay, "tool-number").click()
    click(overlay, 100, 100)
    tb(overlay, "level-0").click()
    assert overlay.marks[0].size == scaled(20, 2.0)


def test_text_gets_the_new_size_and_a_new_box(qtbot):
    overlay = make(qtbot)
    tb(overlay, "tool-text").click()
    qi.press(overlay, 150, 150)
    qi.release(overlay, 150, 150)
    overlay.editor.insert("标注 Ab")
    qi.key(overlay.editor, Qt.Key.Key_Return)
    text = overlay.marks[0]
    tb(overlay, "tool-text").click()  # no tool
    click(overlay, 155, 155)
    assert overlay.picked == 0
    tb(overlay, "level-2").click()
    assert overlay.marks == (fit_text(text, 28),)


def test_fit_text_matches_text_mark():
    small = text_mark("标注 Ab", (10, 20), Style(PALETTE[1], 0), 1.5)
    big = text_mark("标注 Ab", (10, 20), Style(PALETTE[1], 2), 1.5)
    assert fit_text(small, big.size) == big
    nine = fit_text(big, 9)
    assert nine.points[0] == (10, 20) and nine.size == 9 and nine.text == big.text
