"""M4 WI-11: picking, moving and deleting marks, model side (PRD F14-8; plan D8).

Pinned here:
- ``mark_bounds(mark)``: the covered box in physical px. Strokes (rectangle,
  ellipse, arrow, pen) grow by ``ceil(size / 2)`` around their points; text
  and mosaic are their two points; a number is its badge (centre +- size/2).
- ``hit_mark(marks, p, tol)``: index of the last (topmost) mark whose box
  grown by ``tol`` holds ``p`` (edges included), else ``None``.
- ``moved(mark, dx, dy)``: every point shifted, nothing else changed.
- ``Board.change(marks)``: replaces all marks as one undo step.
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from snapocr.annotate import PALETTE, Board, Mark, Tool, hit_mark, mark_bounds, moved
from snapocr.geometry import Rect

R = PALETTE[0]


@pytest.mark.parametrize(
    ("mark", "expected"),
    [
        (Mark(Tool.RECT, ((10, 20), (50, 60)), R, 4), Rect(8, 18, 44, 44)),
        (Mark(Tool.ELLIPSE, ((10, 20), (50, 60)), R, 5), Rect(7, 17, 46, 46)),
        (Mark(Tool.ARROW, ((50, 60), (10, 20)), R, 4), Rect(8, 18, 44, 44)),
        (Mark(Tool.PEN, ((0, 0), (10, 5), (3, 20)), R, 2), Rect(-1, -1, 12, 22)),
        (Mark(Tool.NUMBER, ((100, 100),), R, 28, "1"), Rect(86, 86, 28, 28)),
        (Mark(Tool.NUMBER, ((100, 100),), R, 27, "1"), Rect(86, 86, 28, 28)),
        (Mark(Tool.TEXT, ((10, 10), (60, 30)), R, 20, "hi"), Rect(10, 10, 50, 20)),
        (Mark(Tool.MOSAIC, ((10, 10), (60, 30)), R, 12), Rect(10, 10, 50, 20)),
    ],
)
def test_mark_bounds(mark, expected):
    assert mark_bounds(mark) == expected


A = Mark(Tool.RECT, ((0, 0), (100, 100)), R, 2)
B = Mark(Tool.RECT, ((50, 50), (150, 150)), R, 2)


def test_topmost_mark_wins():
    assert hit_mark((A, B), (75, 75), 0) == 1
    assert hit_mark((B, A), (75, 75), 0) == 1
    assert hit_mark((A, B), (20, 20), 0) == 0


def test_tolerance_and_misses():
    assert hit_mark((A,), (104, 50), 0) is None
    assert hit_mark((A,), (104, 50), 3) == 0
    assert hit_mark((A,), (101, 101), 0) == 0  # edge of the grown box
    assert hit_mark((), (0, 0), 5) is None


def test_moved():
    mark = Mark(Tool.TEXT, ((10, 10), (60, 30)), PALETTE[3], 20, "hi")
    assert moved(mark, -15, 7) == Mark(Tool.TEXT, ((-5, 17), (45, 37)), PALETTE[3], 20, "hi")


@given(st.integers(-100, 100), st.integers(-100, 100))
def test_moved_bounds_move_too(dx, dy):
    b0, b1 = mark_bounds(B), mark_bounds(moved(B, dx, dy))
    assert (b1.x - b0.x, b1.y - b0.y, b1.w, b1.h) == (dx, dy, b0.w, b0.h)


def test_board_change_is_one_undo_step():
    board = Board()
    board.add(A)
    board.add(B)
    board.change((moved(A, 5, 5),))
    assert board.marks == (moved(A, 5, 5),)
    board.undo()
    assert board.marks == (A, B)
