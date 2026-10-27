"""M4 WI-1: annotation model (PRD F14-2, F14-4, F14-6, F14-7; plan D6, D8, D12).

Pinned here:
- ``scaled(value, dpr)``: logical size to physical pixels, half up, at least 1.
- ``Style(color, level)``: color from ``PALETTE``, level 0..2; default red, middle.
- ``drag_mark``: rectangle / ellipse points are normalised to (top-left,
  bottom-right); an arrow keeps its direction; a drag shorter than ``MIN_DRAG``
  physical pixels in both directions gives ``None``; the size is the stroke
  width of the level in physical pixels. Text is not a drag tool.
- ``Board``: marks in drawing order; ``undo`` drops the last change.
- ``arrow_shape`` (F14-9, plan D16): one filled polygon (tail, neck left,
  wing left, tip, wing right, neck right). The tail is the start point, the
  tip the end point. Neck width ``s = min(max(width, L/20), 3*width)``, head
  ``H = min(3s, L/2)`` long and ``1.2H`` wide, neck ``min(s, 0.6H)`` wide,
  both centred on the base of the head, which lies on the line.
- ``toolbar_place``: below the selection, right edges aligned; else above;
  else inside at the bottom; always clamped into the screen area.
"""

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from snapocr.annotate import (
    DEFAULT_STYLE,
    FONT_LEVELS,
    MIN_DRAG,
    PALETTE,
    WIDTH_LEVELS,
    Board,
    Mark,
    Style,
    Tool,
    arrow_shape,
    drag_mark,
    scaled,
    toolbar_place,
)
from snapocr.geometry import Rect

coords = st.integers(-5000, 5000)
points = st.tuples(coords, coords)
dprs = st.sampled_from([1.0, 1.25, 1.5, 1.75, 2.0])
styles = st.builds(Style, st.sampled_from(PALETTE), st.integers(0, 2))
DRAG_TOOLS = (Tool.RECT, Tool.ELLIPSE, Tool.ARROW)


# --- values ----------------------------------------------------------------------


def test_palette_and_levels():
    assert len(PALETTE) == 8 and len(set(PALETTE)) == 8
    assert PALETTE[0] == "#e53935"  # red first: the default
    assert WIDTH_LEVELS == (2, 4, 6)
    assert FONT_LEVELS == (14, 20, 28)
    assert DEFAULT_STYLE == Style(PALETTE[0], 1)


@pytest.mark.parametrize(("value", "dpr", "expected"), [(4, 1.0, 4), (4, 2.0, 8), (4, 1.5, 6), (2, 1.25, 3), (1, 0.25, 1), (6, 1.75, 11)])
def test_scaled(value, dpr, expected):
    assert scaled(value, dpr) == expected


@pytest.mark.parametrize("color", ["red", "#E53935", "#123456", ""])
def test_style_rejects_colors_outside_the_palette(color):
    with pytest.raises(ValueError, match="color"):
        Style(color, 1)


@pytest.mark.parametrize("level", [-1, 3, True, 1.0])
def test_style_rejects_bad_levels(level):
    with pytest.raises(ValueError, match="level"):
        Style(PALETTE[0], level)


# --- drag_mark ---------------------------------------------------------------------


@pytest.mark.parametrize("tool", [Tool.RECT, Tool.ELLIPSE])
def test_box_marks_are_normalised(tool):
    mark = drag_mark(tool, (110, 220), (40, 80), Style(PALETTE[4], 2), 2.0)
    assert mark == Mark(tool, ((40, 80), (110, 220)), PALETTE[4], 12)


def test_arrow_keeps_its_direction():
    mark = drag_mark(Tool.ARROW, (110, 220), (40, 80), DEFAULT_STYLE, 1.5)
    assert mark == Mark(Tool.ARROW, ((110, 220), (40, 80)), PALETTE[0], 6)


@pytest.mark.parametrize("end", [(0, 0), (2, 2), (-2, 2), (2, -2), (0, 2)])
def test_short_drags_leave_nothing(end):
    for tool in DRAG_TOOLS:
        assert drag_mark(tool, (0, 0), end, DEFAULT_STYLE, 1.0) is None


@pytest.mark.parametrize("end", [(3, 0), (0, -3), (3, 3), (-3, 1)])
def test_drags_of_min_length_are_kept(end):
    assert MIN_DRAG == 3
    for tool in DRAG_TOOLS:
        assert drag_mark(tool, (0, 0), end, DEFAULT_STYLE, 1.0) is not None


def test_text_is_not_a_drag_tool():
    with pytest.raises(ValueError, match="text"):
        drag_mark(Tool.TEXT, (0, 0), (50, 50), DEFAULT_STYLE, 1.0)


@given(st.sampled_from([Tool.RECT, Tool.ELLIPSE]), points, points, styles, dprs)
def test_box_marks_ignore_drag_direction(tool, a, b, style, dpr):
    mark = drag_mark(tool, a, b, style, dpr)
    assert mark == drag_mark(tool, b, a, style, dpr)
    if mark is not None:
        (x0, y0), (x1, y1) = mark.points
        assert (x0, y0, x1, y1) == (min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))
        assert mark.size == scaled(WIDTH_LEVELS[style.level], dpr)
        assert mark.color == style.color


# --- Board ---------------------------------------------------------------------------


def mk(i: int) -> Mark:
    return Mark(Tool.RECT, ((i, i), (i + 10, i + 10)), PALETTE[0], 4)


def test_board_add_and_undo():
    board = Board()
    assert board.marks == () and not board.can_undo and board.undo() is False
    board.add(mk(1))
    board.add(mk(2))
    assert board.marks == (mk(1), mk(2)) and board.can_undo
    assert board.undo() is True
    assert board.marks == (mk(1),)
    assert board.undo() is True
    assert board.marks == () and not board.can_undo


@given(st.integers(0, 12), st.data())
def test_undo_k_times_returns_to_k_steps_before(n, data):
    k = data.draw(st.integers(0, n))
    board = Board()
    for i in range(n):
        board.add(mk(i))
    for _ in range(k):
        assert board.undo() is True
    assert board.marks == tuple(mk(i) for i in range(n - k))


# --- arrow_shape ---------------------------------------------------------------------


def test_arrow_shape_horizontal():
    # length 100, width 4: neck 5 (100 / 20), head 15 long and 18 wide
    tail, neck_l, wing_l, tip, wing_r, neck_r = arrow_shape((0, 0), (100, 0), 4)
    assert tail == pytest.approx((0, 0)) and tip == pytest.approx((100, 0))
    assert sorted([neck_l, neck_r]) == [pytest.approx((85, -2.5)), pytest.approx((85, 2.5))]
    assert sorted([wing_l, wing_r]) == [pytest.approx((85, -9)), pytest.approx((85, 9))]


@pytest.mark.parametrize(
    ("length", "width", "neck"), [(40, 4, 4), (100, 4, 5), (240, 4, 12), (1000, 4, 12), (1000, 2, 6), (60, 6, 6)]
)
def test_arrow_neck_grows_with_length_within_the_level(length, width, neck):
    _, neck_l, _, _, _, neck_r = arrow_shape((0, 0), (0, length), width)
    assert math.dist(neck_l, neck_r) == pytest.approx(neck)


def test_short_arrow_head_is_half_the_arrow():
    # neck 4; head min(12, 5) = 5 long, 6 wide; neck min(4, 3) = 3 wide
    _, neck_l, wing_l, _, wing_r, neck_r = arrow_shape((0, 0), (10, 0), 4)
    assert sorted([wing_l, wing_r]) == [pytest.approx((5, -3)), pytest.approx((5, 3))]
    assert sorted([neck_l, neck_r]) == [pytest.approx((5, -1.5)), pytest.approx((5, 1.5))]


def test_zero_length_arrow_is_rejected():
    with pytest.raises(ValueError, match="length"):
        arrow_shape((5, 5), (5, 5), 4)


def _mid(a, b):
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


def _side(start, end, p):
    return (end[0] - start[0]) * (p[1] - start[1]) - (end[1] - start[1]) * (p[0] - start[0])


@given(points, points, st.integers(1, 20))
def test_arrow_shape_geometry(start, end, width):
    length = math.dist(start, end)
    if length == 0:
        return
    neck = min(max(width, length / 20), 3 * width)
    head = min(3 * neck, length / 2)
    tail, neck_l, wing_l, tip, wing_r, neck_r = arrow_shape(start, end, width)
    assert tail == pytest.approx(start) and tip == pytest.approx(end)
    base = _mid(wing_l, wing_r)
    assert math.dist(base, end) == pytest.approx(head)
    assert math.dist(start, base) + math.dist(base, end) == pytest.approx(length)
    assert math.dist(wing_l, wing_r) == pytest.approx(1.2 * head)
    assert _mid(neck_l, neck_r) == pytest.approx(base, abs=1e-6)
    assert math.dist(neck_l, neck_r) == pytest.approx(min(neck, 0.6 * head))
    assert (_side(start, end, neck_l) > 0) == (_side(start, end, wing_l) > 0)


# --- toolbar_place --------------------------------------------------------------------

AREA = Rect(0, 0, 1000, 800)
BAR = (300, 40)


def test_toolbar_below_right_aligned():
    assert toolbar_place(Rect(100, 100, 400, 300), BAR, AREA, 6) == (200, 406)


def test_toolbar_above_when_no_room_below():
    assert toolbar_place(Rect(100, 500, 400, 290), BAR, AREA, 6) == (200, 454)


def test_toolbar_inside_when_no_room_either_side():
    assert toolbar_place(Rect(0, 0, 1000, 800), BAR, AREA, 6) == (700, 754)


def test_toolbar_clamped_to_the_left_edge():
    assert toolbar_place(Rect(10, 100, 50, 50), BAR, AREA, 6) == (0, 156)


def test_toolbar_on_a_screen_not_at_the_origin():
    area = Rect(-1707, -200, 1707, 960)
    assert toolbar_place(Rect(-1707, 600, 1707, 150), BAR, area, 6) == (-300, 554)


@given(st.integers(0, 1000), st.integers(0, 800), st.integers(0, 1000), st.integers(0, 800), st.integers(0, 20))
def test_toolbar_stays_on_screen_and_off_the_selection_when_it_can(x, y, w, h, gap):
    sel = Rect(x, y, min(w, 1000 - x), min(h, 800 - y))  # a selection never leaves its screen
    tx, ty = toolbar_place(sel, BAR, AREA, gap)
    assert AREA.x <= tx and tx + BAR[0] <= AREA.x + AREA.w
    assert AREA.y <= ty and ty + BAR[1] <= AREA.y + AREA.h
    room_below = sel.y + sel.h + gap + BAR[1] <= AREA.y + AREA.h
    room_above = sel.y - gap - BAR[1] >= AREA.y
    if room_below or room_above:
        assert ty >= sel.y + sel.h + gap or ty + BAR[1] <= sel.y - gap
