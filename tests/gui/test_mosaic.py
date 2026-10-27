"""M4 WI-10: mosaic (PRD F14-8; plan D7).

Pinned here:
- ``drag_mark(Tool.MOSAIC, ...)``: a box like the rectangle; size is the block
  side ``scaled(MOSAIC_LEVELS[level], dpr)``.
- Drawing: blocks of ``size`` px starting at the box's top-left corner; every
  pixel of a block has one colour, close to the average of the base pixels
  under it; pixels outside the box (and outside the base image) are
  untouched. The pixels come from ``base``, so marks drawn earlier under a
  mosaic are covered by the picture's own pixels.
- Toolbar button ``tool-mosaic`` (马赛克); dragging with it in the overlay
  adds the mark and the preview shows the blocks.
"""

import pytest
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QToolButton

from snapocr.annotate import MOSAIC_LEVELS, PALETTE, Mark, Style, Tool, drag_mark, scaled
from snapocr.geometry import Rect, ScreenInfo
from snapocr.gui.annotate_toolbar import AnnotateToolbar
from snapocr.gui.marks_paint import render_marked
from snapocr.gui.overlay import SelectionOverlay
from support import qt_input as qi
from support.qimages import gradient

pytestmark = pytest.mark.usefixtures("qapp")

BIG = ScreenInfo("A", Rect(0, 0, 800, 600), 1.0, Rect(0, 0, 800, 600))


def checker(w: int, h: int) -> QImage:
    image = QImage(w, h, QImage.Format.Format_RGB32)
    for y in range(h):
        for x in range(w):
            image.setPixelColor(x, y, QColor("#000000") if (x + y) % 2 else QColor("#ffffff"))
    return image


def block_colours(image: QImage, x0: int, y0: int, b: int) -> set:
    return {image.pixel(x, y) for y in range(y0, y0 + b) for x in range(x0, x0 + b)}


def test_mosaic_levels_and_mark():
    assert MOSAIC_LEVELS == (8, 12, 16)
    mark = drag_mark(Tool.MOSAIC, (100, 80), (20, 10), Style(PALETTE[0], 2), 1.5)
    assert mark == Mark(Tool.MOSAIC, ((20, 10), (100, 80)), PALETTE[0], 24)


def test_blocks_are_flat_and_aligned_to_the_box():
    image = gradient(200, 150)
    out = render_marked(image, [Mark(Tool.MOSAIC, ((20, 30), (100, 90)), PALETTE[0], 10)], (0, 0))
    for bx in range(20, 100, 10):
        for by in range(30, 90, 10):
            assert len(block_colours(out, bx, by, 10)) == 1, (bx, by)
    assert out.pixel(20, 30) != out.pixel(30, 30)


def test_block_colour_is_the_average():
    out = render_marked(checker(100, 100), [Mark(Tool.MOSAIC, ((0, 0), (40, 40)), PALETTE[0], 10)], (0, 0))
    for bx in range(0, 40, 10):
        c = out.pixelColor(bx + 5, 5)
        assert abs(c.red() - 128) <= 24 and abs(c.green() - 128) <= 24 and abs(c.blue() - 128) <= 24


def test_outside_the_box_is_untouched():
    image = gradient(200, 150)
    out = render_marked(image, [Mark(Tool.MOSAIC, ((20, 30), (100, 90)), PALETTE[0], 16)], (0, 0))
    for x, y in [(19, 50), (100, 50), (50, 29), (50, 90), (150, 120)]:
        assert out.pixel(x, y) == image.pixel(x, y), (x, y)
    # 80x60 is not a whole number of 16 px blocks: the last ones are cut at the box edge
    assert len(block_colours(out, 84, 78, 12)) == 1


def test_origin_and_cut_off_box():
    image = gradient(120, 80)
    out = render_marked(image, [Mark(Tool.MOSAIC, ((1080, 540), (1300, 700)), PALETTE[0], 10)], (1000, 500))
    assert len(block_colours(out, 80, 40, 10)) == 1
    assert len(block_colours(out, 110, 70, 10)) == 1
    assert out.pixel(79, 39) == image.pixel(79, 39)


def test_box_off_the_image_draws_nothing():
    image = gradient(120, 80)
    out = render_marked(image, [Mark(Tool.MOSAIC, ((500, 500), (600, 600)), PALETTE[0], 10)], (0, 0))
    assert out == image


def test_mosaic_covers_earlier_marks():
    image = QImage(100, 100, QImage.Format.Format_RGB32)
    image.fill(QColor("#ffffff"))
    marks = [
        Mark(Tool.RECT, ((10, 10), (60, 60)), PALETTE[0], 6),
        Mark(Tool.MOSAIC, ((0, 0), (80, 80)), PALETTE[0], 10),
    ]
    out = render_marked(image, marks, (0, 0))
    assert out.pixelColor(10, 30) == QColor("#ffffff")


def test_toolbar_button():
    bar = AnnotateToolbar()
    b = bar.findChild(QToolButton, "tool-mosaic")
    assert b is not None and "马赛克" in b.toolTip()
    b.click()
    assert bar.tool is Tool.MOSAIC


def test_overlay_draws_a_mosaic(qtbot):
    frozen = gradient(800, 600)
    overlay = SelectionOverlay(frozen, BIG, annotate=True)
    qtbot.addWidget(overlay)
    qi.drag(overlay, 50, 50, 400, 300)
    b = overlay.toolbar.findChild(QToolButton, "tool-mosaic")
    assert b is not None
    b.click()
    qi.drag(overlay, 100, 100, 196, 196)
    size = scaled(MOSAIC_LEVELS[1], 1.0)
    assert overlay.marks == (Mark(Tool.MOSAIC, ((100, 100), (196, 196)), PALETTE[0], size),)
    shot = overlay.grab().toImage()
    assert len(block_colours(shot, 100, 100, size)) == 1
    assert len(block_colours(shot, 100 + size, 100 + size, size)) == 1
