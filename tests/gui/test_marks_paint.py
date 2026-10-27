"""M4 WI-2: drawing annotation marks (PRD F14-7; plan D6, D7).

Pinned here:
- ``render_marked(image, marks, origin)`` returns a new image of the same size
  with the marks drawn on it; ``origin`` is the physical position of the
  image's top-left pixel, so a mark at physical (x, y) lands on image pixel
  (x - origin.x, y - origin.y). The input image is not changed. Marks outside
  the image are cut off.
- Rectangle and ellipse are outlines of ``size`` physical px centred on the
  box edge; the inside is untouched. An arrow is a ``size`` px line plus a
  filled head (``annotate.arrow_head``). Text is drawn from the top-left of
  its box in the mark's colour.
"""

import pytest
from PySide6.QtGui import QColor, QImage

from snapocr.annotate import PALETTE, Mark, Tool
from snapocr.gui.marks_paint import render_marked

pytestmark = pytest.mark.usefixtures("qapp")

RED = QColor(PALETTE[0])
BLUE = QColor(PALETTE[4])
WHITE = QColor("#ffffff")


def canvas(w: int = 200, h: int = 150) -> QImage:
    image = QImage(w, h, QImage.Format.Format_RGB32)
    image.fill(WHITE)
    return image


def at(image: QImage, x: int, y: int) -> QColor:
    return image.pixelColor(x, y)


def is_(color: QColor, expected: QColor) -> bool:
    return (color.red(), color.green(), color.blue()) == (expected.red(), expected.green(), expected.blue())


def test_no_marks_gives_an_identical_copy():
    image = canvas()
    out = render_marked(image, (), (0, 0))
    assert out == image
    assert out is not image


def test_rectangle_outline():
    out = render_marked(canvas(), [Mark(Tool.RECT, ((20, 30), (120, 100)), PALETTE[0], 4)], (0, 0))
    assert (out.width(), out.height()) == (200, 150)
    for x, y in [(20, 60), (120, 60), (70, 30), (70, 100), (19, 60), (21, 60)]:
        assert is_(at(out, x, y), RED), (x, y)
    for x, y in [(70, 65), (24, 60), (16, 60), (70, 104), (150, 120)]:
        assert is_(at(out, x, y), WHITE), (x, y)


def test_stroke_width_is_physical_pixels():
    out = render_marked(canvas(), [Mark(Tool.RECT, ((40, 30), (120, 100)), PALETTE[4], 8)], (0, 0))
    for x in (37, 40, 43):
        assert is_(at(out, x, 60), BLUE), x
    for x in (34, 46):
        assert is_(at(out, x, 60), WHITE), x


def test_origin_shifts_the_marks():
    out = render_marked(canvas(), [Mark(Tool.RECT, ((1020, 530), (1120, 600)), PALETTE[0], 4)], (1000, 500))
    assert is_(at(out, 20, 60), RED)
    assert is_(at(out, 70, 65), WHITE)


def test_negative_origin():
    out = render_marked(canvas(), [Mark(Tool.RECT, ((-2540, 30), (-2440, 100)), PALETTE[0], 4)], (-2560, 0))
    assert is_(at(out, 20, 60), RED)


def test_marks_outside_the_image_are_cut_off():
    out = render_marked(canvas(), [Mark(Tool.RECT, ((150, 100), (400, 300)), PALETTE[0], 4)], (0, 0))
    assert (out.width(), out.height()) == (200, 150)
    assert is_(at(out, 150, 125), RED)
    assert is_(at(out, 199, 100), RED)


def test_input_image_is_unchanged():
    image = canvas()
    before = image.copy()
    render_marked(image, [Mark(Tool.RECT, ((20, 30), (120, 100)), PALETTE[0], 4)], (0, 0))
    assert image == before


def test_ellipse_outline():
    out = render_marked(canvas(), [Mark(Tool.ELLIPSE, ((20, 20), (120, 120)), PALETTE[0], 4)], (0, 0))
    for x, y in [(20, 70), (120, 70), (70, 20), (70, 119)]:
        assert is_(at(out, x, y), RED), (x, y)
    for x, y in [(70, 70), (23, 23), (117, 117)]:
        assert is_(at(out, x, y), WHITE), (x, y)


def test_arrow_line_and_head():
    out = render_marked(canvas(), [Mark(Tool.ARROW, ((20, 75), (180, 75)), PALETTE[0], 4)], (0, 0))
    for x, y in [(60, 75), (60, 76), (166, 80), (166, 70), (176, 75)]:
        assert is_(at(out, x, y), RED), (x, y)
    for x, y in [(60, 79), (166, 84), (185, 75), (10, 75)]:
        assert is_(at(out, x, y), WHITE), (x, y)


def test_text_is_drawn_inside_its_box():
    mark = Mark(Tool.TEXT, ((10, 10), (110, 50)), PALETTE[0], 28, "标注 Ab")
    out = render_marked(canvas(), [mark], (0, 0))
    inked = [(x, y) for y in range(150) for x in range(200) if not is_(at(out, x, y), WHITE)]
    assert len(inked) > 50
    assert all(10 <= x < 130 and 10 <= y < 52 for x, y in inked)
    reddish = [p for p in inked if at(out, *p).red() > 200 and at(out, *p).blue() < 120]
    assert len(reddish) > 20


def test_later_marks_are_drawn_over_earlier_ones():
    marks = [
        Mark(Tool.RECT, ((20, 30), (120, 100)), PALETTE[0], 6),
        Mark(Tool.RECT, ((20, 30), (120, 100)), PALETTE[4], 6),
    ]
    assert is_(at(render_marked(canvas(), marks, (0, 0)), 20, 60), BLUE)
