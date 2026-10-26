"""M2 WI-4: popup placement and thumbnail size (PRD F8-1, F10-1)."""

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from snapocr.geometry import Rect, fit_size, place_popup

AV = Rect(0, 0, 1920, 1040)  # 1920x1080 with a 40 px taskbar
SIZE = (400, 300)


def intersects(a, b):
    return a.x < b.x + b.w and b.x < a.x + a.w and a.y < b.y + b.h and b.y < a.y + a.h


def inside(r, av):
    return av.x <= r.x and av.y <= r.y and r.x + r.w <= av.x + av.w and r.y + r.h <= av.y + av.h


# --- place_popup -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("anchor", "size", "expected"),
    [
        # Middle of the screen: right below, 8 px gap, left-aligned.
        (Rect(800, 400, 300, 200), SIZE, Rect(800, 608, 400, 300)),
        # Touching the bottom: above.
        (Rect(800, 840, 300, 200), SIZE, Rect(800, 532, 400, 300)),
        # Exactly enough room below: 1040 - 300 - 8 = 732.
        (Rect(800, 432, 300, 300), SIZE, Rect(800, 740, 400, 300)),
        # One pixel short below, so above.
        (Rect(800, 433, 300, 300), SIZE, Rect(800, 125, 400, 300)),
        # Full height: to the right, top-aligned.
        (Rect(100, 0, 300, 1040), SIZE, Rect(408, 0, 400, 300)),
        # Full height at the right edge: to the left.
        (Rect(1500, 0, 420, 1040), SIZE, Rect(1092, 0, 400, 300)),
        # Right/left placement clamps vertically.
        (Rect(100, 900, 300, 140), (400, 1000), Rect(408, 40, 400, 1000)),
        # Whole screen: nothing fits, pushed inside and overlapping.
        (Rect(0, 0, 1920, 1040), SIZE, Rect(0, 740, 400, 300)),
        # Near the right edge: shifted left to stay inside.
        (Rect(1800, 100, 100, 50), SIZE, Rect(1520, 158, 400, 300)),
        # Zero-size anchor.
        (Rect(500, 500, 0, 0), SIZE, Rect(500, 508, 400, 300)),
        # Popup larger than the screen: shrunk to it.
        (Rect(800, 400, 300, 200), (5000, 5000), Rect(0, 0, 1920, 1040)),
        (Rect(800, 400, 300, 200), (5000, 100), Rect(0, 608, 1920, 100)),
    ],
)
def test_place_popup_examples(anchor, size, expected):
    assert place_popup(anchor, size, AV) == expected


def test_place_popup_on_negative_screen():
    av = Rect(-2560, 0, 2560, 1400)
    assert place_popup(Rect(-2000, 100, 200, 100), SIZE, av) == Rect(-2000, 208, 400, 300)
    assert place_popup(Rect(-2560, 1300, 50, 100), SIZE, av) == Rect(-2560, 992, 400, 300)


def test_place_popup_gap():
    a = Rect(800, 400, 300, 200)
    assert place_popup(a, SIZE, AV, gap=0) == Rect(800, 600, 400, 300)
    assert place_popup(a, SIZE, AV, gap=20) == Rect(800, 620, 400, 300)


@pytest.mark.parametrize(("size", "gap"), [((-1, 10), 8), ((10, -1), 8), ((10, 10), -1), ((1.5, 10), 8)])
def test_place_popup_rejects_invalid(size, gap):
    with pytest.raises(ValueError):
        place_popup(Rect(0, 0, 10, 10), size, AV, gap=gap)


# --- fit_size --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("src", "box", "expected"),
    [
        ((1920, 1080), (320, 240), (320, 180)),
        ((100, 50), (320, 240), (100, 50)),
        ((320, 240), (320, 240), (320, 240)),
        ((1080, 1920), (320, 240), (135, 240)),
        ((10000, 1), (320, 240), (320, 1)),
        ((1, 10000), (320, 240), (1, 240)),
        ((641, 480), (320, 240), (320, 240)),  # 480 * 320 / 641 = 239.6 -> 240
        ((321, 10), (320, 240), (320, 10)),
    ],
)
def test_fit_size_examples(src, box, expected):
    assert fit_size(src, box) == expected


@pytest.mark.parametrize(("src", "box"), [((0, 10), (320, 240)), ((10, 0), (320, 240)), ((10, 10), (0, 240)),
                                          ((10, 10), (320, -1)), ((10.0, 10), (320, 240))])
def test_fit_size_rejects_invalid(src, box):
    with pytest.raises(ValueError):
        fit_size(src, box)


# --- properties ------------------------------------------------------------------


@st.composite
def layouts(draw):
    av = Rect(draw(st.integers(-5000, 5000)), draw(st.integers(-5000, 5000)),
              draw(st.integers(1, 4000)), draw(st.integers(1, 4000)))
    ax = draw(st.integers(av.x, av.x + av.w))
    ay = draw(st.integers(av.y, av.y + av.h))
    anchor = Rect(ax, ay, draw(st.integers(0, av.x + av.w - ax)), draw(st.integers(0, av.y + av.h - ay)))
    size = (draw(st.integers(0, 5000)), draw(st.integers(0, 5000)))
    gap = draw(st.integers(0, 50))
    return anchor, size, av, gap


@given(layouts())
def test_result_inside_available(layout):
    anchor, size, av, gap = layout
    r = place_popup(anchor, size, av, gap)
    assert inside(r, av)
    assert (r.w, r.h) == (min(size[0], av.w), min(size[1], av.h))


@given(layouts())
def test_no_overlap_when_room_above_or_below(layout):
    anchor, size, av, gap = layout
    h = min(size[1], av.h)
    room_below = av.y + av.h - (anchor.y + anchor.h + gap)
    room_above = anchor.y - gap - av.y
    assume(room_below >= h or room_above >= h)
    assert not intersects(place_popup(anchor, size, av, gap), anchor)


@given(layouts(), st.integers(-3000, 3000), st.integers(-3000, 3000))
def test_translation_equivariant(layout, dx, dy):
    anchor, size, av, gap = layout
    r = place_popup(anchor, size, av, gap)
    moved = place_popup(Rect(anchor.x + dx, anchor.y + dy, anchor.w, anchor.h), size,
                        Rect(av.x + dx, av.y + dy, av.w, av.h), gap)
    assert moved == Rect(r.x + dx, r.y + dy, r.w, r.h)


@given(st.tuples(st.integers(1, 20000), st.integers(1, 20000)), st.tuples(st.integers(1, 2000), st.integers(1, 2000)))
def test_fit_size_bounded_ratio_idempotent(src, box):
    w, h = fit_size(src, box)
    assert 1 <= w <= min(src[0], box[0])
    assert 1 <= h <= min(src[1], box[1])
    # Aspect ratio within 1 px on the derived side.
    assert abs(w * src[1] - h * src[0]) <= max(src)
    assert fit_size((w, h), box) == (w, h)
    if src[0] <= box[0] and src[1] <= box[1]:
        assert (w, h) == src
    else:
        assert w == box[0] or h == box[1]
