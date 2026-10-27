"""M4 WI-19: resizing a text mark by its corner handle, model side (PRD F14-11; plan D18).

Pinned here:
- ``text_handle(mark, tol)``: the bottom-right corner of the mark's box grown
  by ``tol`` (where the picked outline's corner is drawn).
- ``text_resize_size(mark, dx, dy, dpr)``: the font size after the far corner
  moves by ``(dx, dy)`` physical px: the new corner is projected on the box's
  diagonal, the size scales by the same ratio (half up) and is kept within
  ``scaled(8, dpr)`` .. ``scaled(200, dpr)``.
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from snapocr.annotate import PALETTE, Mark, Tool, text_handle, text_resize_size

T = Mark(Tool.TEXT, ((10, 10), (110, 50)), PALETTE[0], 20, "hi")  # 100 x 40


def test_text_handle():
    assert text_handle(T, 4) == (114, 54)
    assert text_handle(T, 0) == (110, 50)


@pytest.mark.parametrize(
    ("dx", "dy", "size"),
    [
        (0, 0, 20),
        (100, 40, 40),
        (-50, -20, 10),
        (100, 0, 37),  # (200*100 + 40*40) / 11600 = 1.862
        (0, 40, 23),  # (100*100 + 80*40) / 11600 = 1.138
        (40, -100, 20),  # across the diagonal: no change
    ],
)
def test_size_follows_the_diagonal(dx, dy, size):
    assert text_resize_size(T, dx, dy, 1.0) == size


@pytest.mark.parametrize(
    ("dx", "dy", "dpr", "size"),
    [
        (-100, -40, 1.0, 8),
        (-500, -500, 2.0, 16),
        (10000, 4000, 1.0, 200),
        (10000, 4000, 1.5, 300),
    ],
)
def test_size_is_kept_in_range(dx, dy, dpr, size):
    assert text_resize_size(T, dx, dy, dpr) == size


@given(st.integers(-200, 400), st.integers(0, 100))
def test_bigger_drag_never_shrinks(t, more):
    a = text_resize_size(T, t, round(t * 0.4), 1.0)
    b = text_resize_size(T, t + more, round((t + more) * 0.4), 1.0)
    assert 8 <= a <= b <= 200
