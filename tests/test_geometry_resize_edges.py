"""M7 WI-4: edge hit test and resize of the frameless translation window (PRD F20-5; M7 plan D8).

Pinned here:
- ``resize_edges(x, y, w, h, margin)`` gives the window edges under a point
  (window-local), as a frozenset of "left" / "top" / "right" / "bottom":
  a corner is two edges; nothing outside the window or deeper than
  ``margin`` from every edge.
- ``resized(rect, edges, dx, dy, min_size)`` moves only the grabbed edges;
  the opposite edges stay put, also when the minimum size stops the drag.
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from snapocr.geometry import Rect, resize_edges, resized

W, H, M = 400, 300, 6
L, T, R, B = "left", "top", "right", "bottom"


@pytest.mark.parametrize(
    ("x", "y", "edges"),
    [
        (200, 150, set()),
        (0, 150, {L}), (5, 150, {L}), (6, 150, set()),
        (399, 150, {R}), (394, 150, {R}), (393, 150, set()),
        (200, 0, {T}), (200, 299, {B}),
        (0, 0, {L, T}), (399, 0, {R, T}), (0, 299, {L, B}), (399, 299, {R, B}), (3, 296, {L, B}),
        (-1, 150, set()), (400, 150, set()), (200, -1, set()), (200, 300, set()),
    ],
)
def test_resize_edges(x, y, edges):
    assert resize_edges(x, y, W, H, M) == frozenset(edges)


def test_resize_edges_on_a_window_thinner_than_two_margins():
    assert resize_edges(2, 50, 8, 100, M) == frozenset({L})  # nearer the left edge
    assert resize_edges(6, 50, 8, 100, M) == frozenset({R})


START = Rect(100, 100, 400, 300)
MIN = (320, 220)


@pytest.mark.parametrize(
    ("edges", "dx", "dy", "want"),
    [
        ({R, B}, 30, 20, Rect(100, 100, 430, 320)),
        ({R}, 30, 20, Rect(100, 100, 430, 300)),
        ({B}, 30, 20, Rect(100, 100, 400, 320)),
        ({L}, -30, 0, Rect(70, 100, 430, 300)),
        ({T}, 0, 25, Rect(100, 125, 400, 275)),
        ({L, T}, 10, 10, Rect(110, 110, 390, 290)),
        ({R, B}, -500, -500, Rect(100, 100, 320, 220)),
        ({L, T}, 500, 500, Rect(180, 180, 320, 220)),  # right and bottom edges stay at 500, 400
        (set(), 30, 20, START),
    ],
)
def test_resized(edges, dx, dy, want):
    assert resized(START, frozenset(edges), dx, dy, MIN) == want


@given(
    st.frozensets(st.sampled_from([L, T, R, B])),
    st.integers(-2000, 2000),
    st.integers(-2000, 2000),
)
def test_resized_keeps_opposite_edges_and_minimum(edges, dx, dy):
    r = resized(START, edges, dx, dy, MIN)
    assert r.w >= MIN[0] and r.h >= MIN[1]
    if L not in edges:
        assert r.x == START.x
    if R not in edges:
        assert r.x + r.w == START.x + START.w or L in edges
    if L in edges and R not in edges:
        assert r.x + r.w == START.x + START.w
    if T in edges and B not in edges:
        assert r.y + r.h == START.y + START.h
    if T not in edges:
        assert r.y == START.y
