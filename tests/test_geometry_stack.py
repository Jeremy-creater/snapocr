"""M9 WI-16: the Mac's per-screen captures side by side, and pairing Qt with CoreGraphics (PRD F23-4, plan D14).

Each screen is grabbed on its own and the images go side by side in Qt's
order: ``x`` adds up, ``y`` is 0. A selection never leaves its screen (F6-4),
so this "physical desktop" needs no real arrangement. Qt screens pair with CG
displays by logical origin and size, since both use the same global points.
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from snapocr.geometry import (
    Rect,
    ScreenInfo,
    ScreenMismatch,
    crop_box,
    local_to_physical,
    pair_displays,
    selection_rect,
    stack_physical,
)

BUILT_IN = ("Built-in Retina Display", Rect(0, 0, 1512, 982), 2.0)
EXTERNAL = ("DELL U2720Q", Rect(1512, -300, 2560, 1440), 1.0)
ABOVE = ("LG", Rect(-200, -1080, 1920, 1080), 1.5)


# --- stack_physical ----------------------------------------------------------------------


def test_one_retina_screen():
    assert stack_physical([BUILT_IN]) == [
        ScreenInfo("Built-in Retina Display", Rect(0, 0, 1512, 982), 2.0, Rect(0, 0, 3024, 1964))
    ]


def test_screens_go_side_by_side_in_qt_order_whatever_their_arrangement():
    assert stack_physical([EXTERNAL, BUILT_IN, ABOVE]) == [
        ScreenInfo("DELL U2720Q", Rect(1512, -300, 2560, 1440), 1.0, Rect(0, 0, 2560, 1440)),
        ScreenInfo("Built-in Retina Display", Rect(0, 0, 1512, 982), 2.0, Rect(2560, 0, 3024, 1964)),
        ScreenInfo("LG", Rect(-200, -1080, 1920, 1080), 1.5, Rect(5584, 0, 2880, 1620)),
    ]


def test_half_pixels_round_up_like_local_to_physical():
    (s,) = stack_physical([("odd", Rect(0, 0, 101, 33), 1.5)])
    assert s.physical == Rect(0, 0, 152, 50)  # 151.5 -> 152, 49.5 -> 50
    assert local_to_physical(s, 101, 33) == (152, 50)


def test_no_screens():
    assert stack_physical([]) == []


DPRS = st.sampled_from([1.0, 1.5, 2.0, 3.0])
QT_SCREEN = st.tuples(
    st.text(min_size=1, max_size=8),
    st.builds(
        Rect,
        st.integers(-5000, 5000),
        st.integers(-5000, 5000),
        st.integers(1, 3000),
        st.integers(1, 2000),
    ),
    DPRS,
)
QT_SCREENS = st.lists(QT_SCREEN, min_size=1, max_size=4)


@given(QT_SCREENS)
def test_stacked_screens_keep_their_size_and_never_overlap(qt):
    screens = stack_physical(qt)
    assert [(s.name, s.logical, s.dpr) for s in screens] == qt
    x = 0
    for s in screens:
        assert s.physical.x == x and s.physical.y == 0
        assert s.physical.w == local_to_physical(s, s.logical.w, 0)[0] - x
        assert s.physical.h == local_to_physical(s, 0, s.logical.h)[1]
        x += s.physical.w
    assert x == sum(s.physical.w for s in screens)  # total width: no gaps, no overlap


@given(QT_SCREENS, st.data())
def test_a_screen_corners_and_selections_stay_on_that_screen(qt, data):
    screens = stack_physical(qt)
    s = data.draw(st.sampled_from(screens))
    p = s.physical
    assert local_to_physical(s, 0, 0) == (p.x, p.y)
    assert local_to_physical(s, s.logical.w, s.logical.h) == (p.x + p.w, p.y + p.h)
    a = (data.draw(st.floats(-50, s.logical.w + 50)), data.draw(st.floats(-50, s.logical.h + 50)))
    b = (data.draw(st.floats(-50, s.logical.w + 50)), data.draw(st.floats(-50, s.logical.h + 50)))
    sel = crop_box(selection_rect(s, local_to_physical(s, *a), local_to_physical(s, *b)), (0, 0))
    assert p.x <= sel.x and sel.x + sel.w <= p.x + p.w
    assert 0 <= sel.y and sel.y + sel.h <= p.h


# --- pair_displays -----------------------------------------------------------------------


def test_pair_by_origin_and_size_in_qt_order():
    displays = [(69734662, Rect(0, 0, 1512, 982)), (5, Rect(1512, -300, 2560, 1440))]
    assert pair_displays([EXTERNAL, BUILT_IN], displays) == [5, 69734662]


def test_qt_rounding_slack_is_allowed():
    assert pair_displays([("A", Rect(0, 0, 1512, 982), 2.0)], [(1, Rect(0, 0, 1513, 981))]) == [1]


def test_no_screens_pair_trivially():
    assert pair_displays([], []) == []


@pytest.mark.parametrize(
    ("qt", "displays", "why"),
    [
        ([BUILT_IN], [], "count"),
        ([BUILT_IN, EXTERNAL], [(1, Rect(0, 0, 1512, 982))], "count"),
        ([BUILT_IN], [(1, Rect(10, 0, 1512, 982))], "no display at"),
        ([BUILT_IN], [(1, Rect(0, 0, 1920, 1080))], "size"),
        # mirroring: two Qt screens on one origin
        ([BUILT_IN, ("Mirror", Rect(0, 0, 1512, 982), 1.0)], [(1, Rect(0, 0, 1512, 982)), (2, Rect(0, 0, 1512, 982))], "same origin"),
    ],
)
def test_screens_that_cannot_be_paired(qt, displays, why):
    with pytest.raises(ScreenMismatch, match=why) as err:
        pair_displays(qt, displays)
    message = str(err.value)
    assert all(name in message for name, _, _ in qt)  # both lists are in the message
    assert all(str(r) in message for _, r in displays)
