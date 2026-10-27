"""M4 WI-9: number badges and freehand pen, drawing and overlay (PRD F14-8).

Pinned here:
- A number mark is a filled circle of diameter ``size`` in the mark's colour
  centred on its point, with the number in white (black on yellow and white).
- A pen mark is a ``size`` px line through its points.
- Toolbar buttons ``tool-number`` (序号) and ``tool-pen`` (画笔).
- Number tool: a left press inside the selection adds
  ``number_mark(press, marks, style, dpr)`` at once; outside adds nothing.
- Pen tool: a drag inside the selection adds ``pen_mark(press + every move +
  release, style, dpr)``; the draft is shown while dragging.
"""

import pytest
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QToolButton

from snapocr.annotate import DEFAULT_STYLE, PALETTE, Mark, Style, Tool, number_mark, pen_mark
from snapocr.geometry import Rect, ScreenInfo, local_to_physical
from snapocr.gui.annotate_toolbar import AnnotateToolbar
from snapocr.gui.marks_paint import render_marked
from snapocr.gui.overlay import SelectionOverlay
from support import qt_input as qi

pytestmark = pytest.mark.usefixtures("qapp")

WHITE = QColor("#ffffff")
GREY = QColor(200, 200, 200)
BIG = ScreenInfo("A", Rect(0, 0, 800, 600), 1.0, Rect(0, 0, 800, 600))
HI = ScreenInfo("B", Rect(800, 0, 400, 300), 2.0, Rect(1600, 0, 800, 600))


def canvas() -> QImage:
    image = QImage(200, 150, QImage.Format.Format_RGB32)
    image.fill(WHITE)
    return image


def rgb(c: QColor):
    return c.red(), c.green(), c.blue()


# --- drawing -------------------------------------------------------------------------


def test_number_badge():
    out = render_marked(canvas(), [Mark(Tool.NUMBER, ((100, 75),), PALETTE[4], 40, "7")], (0, 0))
    ring = [(100, 58), (83, 75), (117, 75), (100, 92), (88, 63)]
    assert all(rgb(out.pixelColor(x, y)) == rgb(QColor(PALETTE[4])) for x, y in ring)
    assert rgb(out.pixelColor(100, 50)) == rgb(WHITE) and rgb(out.pixelColor(75, 75)) == rgb(WHITE)
    digit = [(x, y) for y in range(65, 86) for x in range(90, 111) if out.pixelColor(x, y).lightness() > 200]
    assert len(digit) > 10  # white digit on blue


def test_number_on_yellow_is_dark():
    out = render_marked(canvas(), [Mark(Tool.NUMBER, ((100, 75),), PALETTE[2], 40, "8")], (0, 0))
    dark = [(x, y) for y in range(65, 86) for x in range(90, 111) if out.pixelColor(x, y).lightness() < 80]
    assert len(dark) > 10


def test_pen_stroke():
    mark = Mark(Tool.PEN, ((20, 20), (100, 20), (100, 120)), PALETTE[0], 4)
    out = render_marked(canvas(), [mark], (0, 0))
    for x, y in [(60, 20), (60, 21), (100, 70), (99, 70), (100, 20)]:
        assert rgb(out.pixelColor(x, y)) == rgb(QColor(PALETTE[0])), (x, y)
    for x, y in [(60, 25), (60, 60), (105, 70), (20, 120)]:
        assert rgb(out.pixelColor(x, y)) == rgb(WHITE), (x, y)


# --- toolbar ---------------------------------------------------------------------------


@pytest.mark.parametrize(("name", "tool", "tip"), [("tool-number", Tool.NUMBER, "序号"), ("tool-pen", Tool.PEN, "画笔")])
def test_toolbar_buttons(name, tool, tip):
    bar = AnnotateToolbar()
    b = bar.findChild(QToolButton, name)
    assert b is not None, name
    assert tip in b.toolTip()
    seen = []
    bar.tool_changed.connect(seen.append)
    b.click()
    assert seen == [tool] and bar.tool is tool


# --- overlay ---------------------------------------------------------------------------


@pytest.fixture
def pick(qtbot):
    def factory(name, screen=BIG):
        image = QImage(screen.physical.w, screen.physical.h, QImage.Format.Format_RGB32)
        image.fill(GREY)
        overlay = SelectionOverlay(image, screen, annotate=True)
        qtbot.addWidget(overlay)
        qi.drag(overlay, 50, 50, 300, 250)
        b = overlay.toolbar.findChild(QToolButton, name)
        assert b is not None, name
        b.click()
        return overlay

    return factory


def test_number_tool_adds_badges_on_press(pick):
    overlay = pick("tool-number")
    qi.press(overlay, 100, 100)
    assert overlay.marks == (number_mark((100, 100), (), DEFAULT_STYLE, 1.0),)
    qi.release(overlay, 100, 100)
    qi.press(overlay, 150, 120)
    qi.release(overlay, 150, 120)
    assert [m.text for m in overlay.marks] == ["1", "2"]
    assert overlay.toolbar.findChild(QToolButton, "undo").isEnabled()


def test_number_tool_outside_adds_nothing(pick):
    overlay = pick("tool-number")
    qi.press(overlay, 400, 400)
    qi.release(overlay, 400, 400)
    assert overlay.marks == ()


def test_number_size_on_a_scaled_screen(pick):
    overlay = pick("tool-number", HI)
    overlay.toolbar.findChild(QToolButton, "level-2").click()
    qi.press(overlay, 100, 100)
    assert overlay.marks == (Mark(Tool.NUMBER, (local_to_physical(HI, 100, 100),), PALETTE[0], 72, "1"),)


def test_pen_tool_draws_through_every_point(pick):
    overlay = pick("tool-pen")
    qi.press(overlay, 100, 100)
    qi.move(overlay, 120, 110)
    qi.move(overlay, 140, 100)
    qi.move(overlay, 140, 100)
    qi.release(overlay, 160, 130)
    pts = [(100, 100), (120, 110), (140, 100), (140, 100), (160, 130)]
    assert overlay.marks == (pen_mark(pts, DEFAULT_STYLE, 1.0),)


def test_pen_draft_is_painted(pick):
    overlay = pick("tool-pen")
    overlay.toolbar.findChild(QToolButton, "color-4").click()
    qi.press(overlay, 100, 150)
    qi.move(overlay, 200, 150)
    image = overlay.grab().toImage()
    assert rgb(image.pixelColor(150, 150)) == rgb(QColor(PALETTE[4]))
    assert overlay.marks == ()


def test_tiny_pen_stroke_leaves_nothing(pick):
    overlay = pick("tool-pen")
    qi.press(overlay, 100, 100)
    qi.move(overlay, 101, 101)
    qi.release(overlay, 101, 102)
    assert overlay.marks == ()


def test_pen_style(pick):
    overlay = pick("tool-pen")
    overlay.toolbar.findChild(QToolButton, "level-0").click()
    qi.drag(overlay, 100, 100, 200, 200)
    assert overlay.marks[0].size == 2 and overlay.marks[0].color == Style().color
