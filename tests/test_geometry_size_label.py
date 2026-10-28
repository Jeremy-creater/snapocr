"""M5 WI-6: the selection size label, pure part (PRD F18-6; M5 plan D8).

Pinned here:
- ``size_text(rect)`` is "W × H" of the rect (physical pixels), with the
  multiplication sign and a space on each side.
- ``label_place(sel, size, bounds, gap)`` (logical px) puts the label above
  the selection, left edges aligned, ``gap`` between them; when that leaves
  ``bounds`` at the top, inside the selection at its top-left (``gap`` in).
  ``x`` is clamped so the label stays inside ``bounds`` left and right (when
  it is not wider than ``bounds``).
"""

from hypothesis import assume, given
from hypothesis import strategies as st

from snapocr.geometry import Rect, label_place, size_text

SCREEN = Rect(0, 0, 800, 600)
GAP = 4


def test_size_text():
    assert size_text(Rect(10, 20, 1280, 720)) == "1280 × 720"
    assert size_text(Rect(0, 0, 4, 4)) == "4 × 4"


def test_above_the_selection_left_aligned():
    assert label_place(Rect(100, 100, 200, 150), (80, 20), SCREEN, GAP) == (100, 76)


def test_inside_when_there_is_no_room_above():
    assert label_place(Rect(100, 10, 200, 150), (80, 20), SCREEN, GAP) == (100, 14)
    assert label_place(Rect(100, 23, 200, 150), (80, 20), SCREEN, GAP) == (100, 27)
    assert label_place(Rect(100, 24, 200, 150), (80, 20), SCREEN, GAP) == (100, 0)  # just fits above


def test_clamped_inside_the_screen_sideways():
    assert label_place(Rect(780, 100, 20, 20), (80, 20), SCREEN, GAP) == (720, 76)
    assert label_place(Rect(-5, 100, 20, 20), (80, 20), Rect(0, 0, 800, 600), GAP) == (0, 76)


def test_on_a_screen_not_at_the_origin():
    side = Rect(800, -200, 400, 300)
    assert label_place(Rect(1150, -190, 50, 50), (80, 20), side, GAP) == (1120, -186)


@st.composite
def cases(draw):
    bx, by = draw(st.integers(-2000, 2000)), draw(st.integers(-2000, 2000))
    bw, bh = draw(st.integers(100, 4000)), draw(st.integers(100, 3000))
    w, h = draw(st.integers(1, bw)), draw(st.integers(1, 40))
    sw, sh = draw(st.integers(1, bw)), draw(st.integers(1, bh))
    sx, sy = draw(st.integers(bx, bx + bw - sw)), draw(st.integers(by, by + bh - sh))
    return Rect(sx, sy, sw, sh), (w, h), Rect(bx, by, bw, bh), draw(st.integers(0, 10))


@given(cases())
def test_the_label_stays_inside_the_screen_sideways(case):
    sel, (w, h), bounds, gap = case
    x, _ = label_place(sel, (w, h), bounds, gap)
    assert bounds.x <= x <= bounds.x + bounds.w - w


@given(cases())
def test_above_never_overlaps_and_inside_starts_at_the_top(case):
    sel, (w, h), bounds, gap = case
    _, y = label_place(sel, (w, h), bounds, gap)
    if sel.y - gap - h >= bounds.y:
        assert y + h + gap == sel.y
    else:
        assert y == sel.y + gap


@given(cases())
def test_left_aligned_unless_clamped(case):
    sel, (w, h), bounds, gap = case
    assume(sel.x + w <= bounds.x + bounds.w)
    x, _ = label_place(sel, (w, h), bounds, gap)
    assert x == sel.x
