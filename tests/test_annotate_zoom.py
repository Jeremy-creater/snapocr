"""M4 WI-7: zoom of a pinned screenshot (PRD F15-2; plan D14).

Pinned here:
- ``zoom_percent(current, steps)``: ``current + 10 * steps`` clamped to 10..500.
- ``zoom_rect(rect, anchor, base, percent)``: the window rect (logical) at
  ``percent`` of ``base`` (each side rounded half up, at least 1), placed so
  the anchor point keeps its relative position inside the window (the point
  under the mouse does not move), rounded half up.
"""

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from snapocr.annotate import ZOOM_MAX, ZOOM_MIN, ZOOM_STEP, zoom_percent, zoom_rect
from snapocr.geometry import Rect


@pytest.mark.parametrize(
    ("current", "steps", "expected"),
    [(100, 1, 110), (100, -1, 90), (100, 3, 130), (100, 0, 100), (10, -1, 10), (20, -5, 10), (500, 1, 500), (490, 4, 500)],
)
def test_zoom_percent(current, steps, expected):
    assert zoom_percent(current, steps) == expected


def test_zoom_limits():
    assert (ZOOM_MIN, ZOOM_MAX, ZOOM_STEP) == (10, 500, 10)


@given(st.integers(1, 50).map(lambda n: n * 10), st.integers(-60, 60))
def test_zoom_percent_stays_on_the_grid(current, steps):
    z = zoom_percent(current, steps)
    assert ZOOM_MIN <= z <= ZOOM_MAX and z % ZOOM_STEP == 0


def test_zoom_about_the_centre():
    assert zoom_rect(Rect(100, 100, 200, 100), (200, 150), (200, 100), 200) == Rect(0, 50, 400, 200)


def test_zoom_about_the_top_left_corner():
    assert zoom_rect(Rect(100, 100, 200, 100), (100, 100), (200, 100), 50) == Rect(100, 100, 100, 50)


def test_zoom_from_a_zoomed_window():
    # at 50% (100x50) with the mouse at the right edge, back to 100%
    assert zoom_rect(Rect(100, 100, 100, 50), (200, 125), (200, 100), 100) == Rect(0, 75, 200, 100)


def test_tiny_sizes_stay_at_least_one_pixel():
    assert zoom_rect(Rect(0, 0, 5, 3), (0, 0), (5, 3), 10) == Rect(0, 0, 1, 1)


@given(
    st.integers(-3000, 3000),
    st.integers(-3000, 3000),
    st.integers(20, 2000),
    st.integers(20, 2000),
    st.floats(0, 1),
    st.floats(0, 1),
    st.integers(1, 50).map(lambda n: n * 10),
)
def test_anchor_keeps_its_place(x, y, w, h, fx, fy, percent):
    rect = Rect(x, y, w, h)
    anchor = (x + fx * w, y + fy * h)
    out = zoom_rect(rect, anchor, (w, h), percent)
    assert (out.w, out.h) == (max(1, math.floor(w * percent / 100 + 0.5)), max(1, math.floor(h * percent / 100 + 0.5)))
    assert abs(out.x + fx * out.w - anchor[0]) <= 0.5 + 1e-9
    assert abs(out.y + fy * out.h - anchor[1]) <= 0.5 + 1e-9
