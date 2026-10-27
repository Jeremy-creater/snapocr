"""M4 WI-9: number badges and freehand pen, model side (PRD F14-8; plan D8).

Pinned here:
- ``next_number(marks)``: one more than the largest number mark, 1 when there
  is none (so undoing the last badge brings its number back).
- ``number_mark(center, marks, style, dpr)``: a ``Tool.NUMBER`` mark at
  ``center`` whose size is the badge diameter ``scaled(NUMBER_LEVELS[level],
  dpr)`` and whose text is ``next_number(marks)``.
- ``pen_mark(points, style, dpr)``: consecutive repeats dropped; ``None`` when
  no point gets ``MIN_DRAG`` px (either axis) from the first; size is the
  stroke width of the level.
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from snapocr.annotate import (
    DEFAULT_STYLE,
    NUMBER_LEVELS,
    PALETTE,
    WIDTH_LEVELS,
    Board,
    Mark,
    Style,
    Tool,
    next_number,
    number_mark,
    pen_mark,
    scaled,
)


def badge(n: int) -> Mark:
    return Mark(Tool.NUMBER, ((n, n),), PALETTE[0], 28, str(n))


RECT = Mark(Tool.RECT, ((0, 0), (10, 10)), PALETTE[0], 4)


def test_number_levels():
    assert NUMBER_LEVELS == (20, 28, 36)


@pytest.mark.parametrize(
    ("marks", "expected"),
    [((), 1), ((RECT,), 1), ((badge(1),), 2), ((badge(1), RECT, badge(2)), 3), ((badge(4), badge(2)), 5)],
)
def test_next_number(marks, expected):
    assert next_number(marks) == expected


def test_number_mark():
    mark = number_mark((-50, 70), (badge(1), badge(2)), Style(PALETTE[2], 2), 1.5)
    assert mark == Mark(Tool.NUMBER, ((-50, 70),), PALETTE[2], 54, "3")


def test_numbers_go_back_after_undo():
    board = Board()
    for i in range(3):
        board.add(number_mark((i * 40, 0), board.marks, DEFAULT_STYLE, 1.0))
    assert [m.text for m in board.marks] == ["1", "2", "3"]
    board.undo()
    board.add(number_mark((0, 90), board.marks, DEFAULT_STYLE, 1.0))
    assert [m.text for m in board.marks] == ["1", "2", "3"]


def test_pen_mark_drops_repeats():
    mark = pen_mark([(0, 0), (0, 0), (2, 1), (2, 1), (5, 4), (2, 1)], Style(PALETTE[4], 0), 2.0)
    assert mark == Mark(Tool.PEN, ((0, 0), (2, 1), (5, 4), (2, 1)), PALETTE[4], 4)


@pytest.mark.parametrize("points", [[], [(5, 5)], [(5, 5), (7, 7), (3, 3)], [(0, 0), (2, -2), (-2, 2)]])
def test_short_strokes_leave_nothing(points):
    assert pen_mark(points, DEFAULT_STYLE, 1.0) is None


def test_stroke_that_comes_back_is_kept():
    assert pen_mark([(0, 0), (0, 3), (0, 0)], DEFAULT_STYLE, 1.0) is not None


@given(st.lists(st.tuples(st.integers(-50, 50), st.integers(-50, 50)), max_size=30), st.integers(0, 2))
def test_pen_mark_properties(points, level):
    mark = pen_mark(points, Style(PALETTE[0], level), 1.0)
    far = max((max(abs(x - points[0][0]), abs(y - points[0][1])) for x, y in points), default=0)
    if far < 3:
        assert mark is None
        return
    assert mark.size == scaled(WIDTH_LEVELS[level], 1.0)
    assert all(a != b for a, b in zip(mark.points, mark.points[1:]))
    assert set(mark.points) == set(points)
    assert mark.points[0] == points[0] and mark.points[-1] == points[-1]
