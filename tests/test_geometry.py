"""M2 WI-3: screen and selection geometry (PRD F6-2 to F6-5)."""

import ast
import math
import sys
from pathlib import Path

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from snapocr.geometry import (
    Handle,
    Rect,
    ScreenInfo,
    ScreenMismatch,
    crop_box,
    hit_handle,
    is_cancel_size,
    local_to_physical,
    match_screens,
    move,
    physical_to_local,
    resize,
    selection_rect,
)

PRIMARY = ScreenInfo("DISPLAY1", Rect(0, 0, 1920, 1080), 1.0, Rect(0, 0, 1920, 1080))
LEFT = ScreenInfo("DISPLAY2", Rect(-1707, 0, 1707, 960), 1.5, Rect(-2560, 0, 2560, 1440))
# Jeremy's desk (PRD F6-2): 200% and 150%; positions to be confirmed by WI-20.
JA = ScreenInfo("A", Rect(0, 0, 1920, 1080), 2.0, Rect(0, 0, 3840, 2160))
JB = ScreenInfo("B", Rect(1920, 0, 1707, 960), 1.5, Rect(3840, 0, 2560, 1440))


def drag(screen, a, b):
    return selection_rect(screen, local_to_physical(screen, *a), local_to_physical(screen, *b))


# --- value types -----------------------------------------------------------------


@pytest.mark.parametrize("args", [(0, 0, -1, 1), (0, 0, 1, -1), (0.0, 0, 1, 1), (0, True, 1, 1), (0, 0, "1", 1)])
def test_rect_rejects_invalid(args):
    with pytest.raises(ValueError):
        Rect(*args)


@pytest.mark.parametrize("dpr", [0.0, -1.0, math.inf, math.nan, "2"])
def test_screen_rejects_invalid_dpr(dpr):
    with pytest.raises(ValueError):
        ScreenInfo("X", Rect(0, 0, 10, 10), dpr, Rect(0, 0, 10, 10))


def test_rect_zero_size_allowed():
    assert Rect(-5, -5, 0, 0).w == 0


# --- match_screens ---------------------------------------------------------------


def test_match_two_screens():
    qt = [(LEFT.name, LEFT.logical, 1.5), (PRIMARY.name, PRIMARY.logical, 1.0)]
    mons = [(PRIMARY.name, PRIMARY.physical), (LEFT.name, LEFT.physical)]
    assert match_screens(qt, mons) == [LEFT, PRIMARY]


def test_match_jeremy_screens():
    qt = [("A", JA.logical, 2.0), ("B", JB.logical, 1.5)]
    assert match_screens(qt, [("B", JB.physical), ("A", JA.physical)]) == [JA, JB]


def test_match_empty():
    assert match_screens([], []) == []


@pytest.mark.parametrize(
    ("qt", "mons"),
    [
        ([("A", JA.logical, 2.0)], [("A", JA.physical), ("B", JB.physical)]),  # extra monitor
        ([("A", JA.logical, 2.0), ("B", JB.logical, 1.5)], [("A", JA.physical)]),  # missing monitor
        ([("A", JA.logical, 2.0)], [("Z", JA.physical)]),  # different name
        ([("A", JA.logical, 2.0), ("A", JA.logical, 2.0)], [("A", JA.physical), ("A", JA.physical)]),  # duplicate
        ([("A", JA.logical, 1.0)], [("A", JA.physical)]),  # width 3840 / 1.0 != 1920
        ([("A", Rect(0, 0, 1920, 1000), 2.0)], [("A", JA.physical)]),  # height 1080 != 1000
        ([("B", Rect(0, 0, 1709, 960), 1.5)], [("B", JB.physical)]),  # 1706.67 vs 1709: off by > 1
    ],
)
def test_match_mismatch(qt, mons):
    with pytest.raises(ScreenMismatch):
        match_screens(qt, mons)


@pytest.mark.parametrize("logical_w", [1706, 1707])
def test_match_tolerates_rounding(logical_w):
    (s,) = match_screens([("B", Rect(0, 0, logical_w, 960), 1.5)], [("B", JB.physical)])
    assert s.physical == JB.physical


# --- coordinate conversion -------------------------------------------------------


def test_drag_on_left_screen():
    assert drag(LEFT, (100, 100), (200, 150)) == Rect(-2410, 150, 150, 75)


def test_drag_on_jeremy_screens():
    assert drag(JA, (100, 100), (300, 200)) == Rect(200, 200, 400, 200)
    # 10.5 * 1.5 = 15.75 -> 16; 110.5 * 1.5 = 165.75 -> 166
    assert drag(JB, (10.5, 20), (110.5, 120)) == Rect(3856, 30, 150, 150)


@pytest.mark.parametrize(
    ("dpr", "x", "expected"),
    [(1.0, 7, 7), (1.25, 3, 4), (1.25, 2, 3), (1.5, 1, 2), (1.75, 2, 4), (2.0, 0.25, 1), (2.0, 0.24, 0)],
)
def test_local_to_physical_rounding(dpr, x, expected):
    s = ScreenInfo("S", Rect(0, 0, 100, 100), dpr, Rect(-50, 10, round(100 * dpr), round(100 * dpr)))
    assert local_to_physical(s, x, x) == (-50 + expected, 10 + expected)


def test_physical_to_local_example():
    assert physical_to_local(LEFT, -2410, 150) == pytest.approx((100.0, 100.0))
    assert physical_to_local(JB, 3840, 0) == (0.0, 0.0)


# --- selection_rect / cancel / crop ---------------------------------------------


def test_reverse_drag_same():
    assert drag(LEFT, (200, 150), (100, 100)) == drag(LEFT, (100, 100), (200, 150))
    assert drag(LEFT, (200, 100), (100, 150)) == Rect(-2410, 150, 150, 75)


def test_drag_out_of_screen_clipped():
    assert selection_rect(LEFT, (-3000, -50), (-2500, 2000)) == Rect(-2560, 0, 60, 1440)
    assert selection_rect(PRIMARY, (1900, 1000), (5000, 5000)) == Rect(1900, 1000, 20, 80)


def test_selection_at_screen_edge_and_zero():
    assert selection_rect(PRIMARY, (0, 0), (1920, 1080)) == Rect(0, 0, 1920, 1080)
    assert selection_rect(PRIMARY, (5, 5), (5, 5)) == Rect(5, 5, 0, 0)
    assert selection_rect(PRIMARY, (-10, 5), (-1, 9)) == Rect(0, 5, 0, 4)


@pytest.mark.parametrize(
    ("w", "h", "cancel"), [(3, 100, True), (100, 3, True), (0, 0, True), (4, 4, False), (4, 3, True), (500, 4, False)]
)
def test_is_cancel_size(w, h, cancel):
    assert is_cancel_size(Rect(0, 0, w, h)) is cancel


def test_crop_box_example():
    assert crop_box(Rect(-2410, 150, 150, 75), virtual_origin=(-2560, 0)) == Rect(150, 150, 150, 75)
    assert crop_box(Rect(3856, 30, 150, 150), virtual_origin=(0, 0)) == Rect(3856, 30, 150, 150)


# --- F6-5: handles, resize, move -------------------------------------------------

R = Rect(100, 100, 200, 100)  # x 100..300, y 100..200


@pytest.mark.parametrize(
    ("p", "expected"),
    [
        ((100, 100), Handle.NW), ((300, 100), Handle.NE), ((100, 200), Handle.SW), ((300, 200), Handle.SE),
        ((95, 95), Handle.NW), ((305, 205), Handle.SE), ((94, 100), Handle.NONE), ((306, 205), Handle.NONE),
        ((200, 100), Handle.N), ((200, 200), Handle.S), ((100, 150), Handle.W), ((300, 150), Handle.E),
        ((200, 95), Handle.N), ((200, 205), Handle.S), ((95, 150), Handle.W), ((305, 150), Handle.E),
        ((200, 94), Handle.NONE), ((200, 206), Handle.NONE), ((94, 150), Handle.NONE), ((306, 150), Handle.NONE),
        ((106, 106), Handle.INSIDE), ((200, 150), Handle.INSIDE), ((294, 194), Handle.INSIDE),
        ((106, 105), Handle.N), ((105, 106), Handle.W),
        ((0, 0), Handle.NONE), ((200, 1000), Handle.NONE),
    ],
)
def test_hit_handle_regions(p, expected):
    assert hit_handle(R, p, 5) == expected


def test_hit_handle_zero_tolerance():
    assert hit_handle(R, (100, 100), 0) == Handle.NW
    assert hit_handle(R, (101, 100), 0) == Handle.N
    assert hit_handle(R, (101, 101), 0) == Handle.INSIDE
    assert hit_handle(R, (99, 150), 0) == Handle.NONE


def test_hit_handle_tiny_rect_picks_nearest_corner():
    tiny = Rect(100, 100, 4, 4)
    assert hit_handle(tiny, (105, 105), 5) == Handle.SE
    assert hit_handle(tiny, (99, 99), 5) == Handle.NW
    assert hit_handle(tiny, (105, 99), 5) == Handle.NE
    assert hit_handle(tiny, (99, 105), 5) == Handle.SW
    # Equidistant from all four corners: ties go SE, SW, NE, NW.
    assert hit_handle(tiny, (102, 102), 5) == Handle.SE
    assert hit_handle(Rect(100, 100, 0, 0), (100, 100), 5) == Handle.SE


def test_hit_handle_thin_rect_picks_nearest_edge():
    thin = Rect(100, 100, 200, 6)  # corners need |dx| <= 2 at tol 2
    assert hit_handle(thin, (200, 101), 2) == Handle.N
    assert hit_handle(thin, (200, 105), 2) == Handle.S
    # Equidistant from N and S: ties go S, E, N, W.
    assert hit_handle(thin, (200, 103), 3) == Handle.S
    assert hit_handle(Rect(100, 100, 6, 200), (103, 200), 3) == Handle.E


def test_hit_handle_rejects_negative_tol():
    with pytest.raises(ValueError):
        hit_handle(R, (0, 0), -1)


@pytest.mark.parametrize(
    ("handle", "p", "expected"),
    [
        (Handle.SE, (400, 300), Rect(100, 100, 300, 200)),
        (Handle.SE, (300, 200), R),
        (Handle.NW, (50, 60), Rect(50, 60, 250, 140)),
        (Handle.NE, (350, 150), Rect(100, 150, 250, 50)),
        (Handle.SW, (120, 250), Rect(120, 100, 180, 150)),
        (Handle.E, (350, 9999), Rect(100, 100, 250, 100)),
        (Handle.W, (150, -5), Rect(150, 100, 150, 100)),
        (Handle.N, (-5, 150), Rect(100, 150, 200, 50)),
        (Handle.S, (9999, 120), Rect(100, 100, 200, 20)),
        # Dragged past the opposite edge: the box flips.
        (Handle.E, (40, 0), Rect(40, 100, 60, 100)),
        (Handle.N, (0, 260), Rect(100, 200, 200, 60)),
        (Handle.NW, (400, 300), Rect(300, 200, 100, 100)),
        # Onto the opposite edge: zero size, which F6-3 treats as cancel.
        (Handle.E, (100, 0), Rect(100, 100, 0, 100)),
        (Handle.S, (0, 100), Rect(100, 100, 200, 0)),
        # Off the screen: clipped.
        (Handle.SE, (5000, 5000), Rect(100, 100, 1820, 980)),
        (Handle.W, (-300, 0), Rect(0, 100, 300, 100)),
    ],
)
def test_resize(handle, p, expected):
    assert resize(R, handle, p, PRIMARY) == expected


@pytest.mark.parametrize("handle", [Handle.NONE, Handle.INSIDE])
def test_resize_rejects_non_edge_handles(handle):
    with pytest.raises(ValueError):
        resize(R, handle, (0, 0), PRIMARY)


@pytest.mark.parametrize(
    ("d", "expected"),
    [
        ((10, -20), Rect(110, 80, 200, 100)),
        ((0, 0), R),
        ((-500, 0), Rect(0, 100, 200, 100)),
        ((5000, 5000), Rect(1720, 980, 200, 100)),
        ((-5000, -5000), Rect(0, 0, 200, 100)),
    ],
)
def test_move(d, expected):
    assert move(R, *d, PRIMARY) == expected


def test_move_on_negative_screen():
    assert move(Rect(-2410, 150, 150, 75), -1000, 2000, LEFT) == Rect(-2560, 1365, 150, 75)


def test_move_full_screen_rect_stays():
    assert move(PRIMARY.physical, 30, -30, PRIMARY) == PRIMARY.physical


def test_move_rejects_rect_off_screen():
    with pytest.raises(ValueError):
        move(Rect(1900, 0, 100, 100), 0, 0, PRIMARY)


# --- properties ------------------------------------------------------------------


@st.composite
def screens(draw):
    dpr = draw(st.sampled_from([1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0]) | st.floats(0.5, 4.0))
    x = draw(st.integers(-8000, 8000))
    y = draw(st.integers(-8000, 8000))
    w = draw(st.integers(1, 8000))
    h = draw(st.integers(1, 8000))
    return ScreenInfo("S", Rect(0, 0, max(1, round(w / dpr)), max(1, round(h / dpr))), dpr, Rect(x, y, w, h))


def points_in(screen):
    p = screen.physical
    return st.tuples(st.integers(p.x, p.x + p.w), st.integers(p.y, p.y + p.h))


def anywhere(screen):
    p = screen.physical
    return st.tuples(st.integers(p.x - 3000, p.x + p.w + 3000), st.integers(p.y - 3000, p.y + p.h + 3000))


@st.composite
def screen_and_rect(draw):
    s = draw(screens())
    a = draw(points_in(s))
    b = draw(points_in(s))
    return s, selection_rect(s, a, b)


def inside(r, screen):
    p = screen.physical
    return p.x <= r.x and p.y <= r.y and r.x + r.w <= p.x + p.w and r.y + r.h <= p.y + p.h


@given(st.data())
def test_roundtrip_physical_local(data):
    s = data.draw(screens())
    px, py = data.draw(points_in(s))
    assert local_to_physical(s, *physical_to_local(s, px, py)) == (px, py)


@given(screens(), st.floats(-5000, 5000), st.floats(-5000, 5000))
def test_monotonic(s, x1, x2):
    lo, hi = sorted((x1, x2))
    (a, b), (c, d) = local_to_physical(s, lo, lo), local_to_physical(s, hi, hi)
    assert a <= c and b <= d


@given(st.data())
def test_selection_symmetric_inside_idempotent(data):
    s = data.draw(screens())
    a = data.draw(anywhere(s))
    b = data.draw(anywhere(s))
    r = selection_rect(s, a, b)
    assert r == selection_rect(s, b, a)
    assert inside(r, s)
    assert selection_rect(s, (r.x, r.y), (r.x + r.w, r.y + r.h)) == r


@given(st.data())
def test_selection_inside_screen_is_exact(data):
    s = data.draw(screens())
    (ax, ay), (bx, by) = data.draw(points_in(s)), data.draw(points_in(s))
    assert selection_rect(s, (ax, ay), (bx, by)) == Rect(min(ax, bx), min(ay, by), abs(ax - bx), abs(ay - by))


@given(screen_and_rect(), st.integers(0, 3000), st.integers(0, 3000))
def test_crop_box_in_bounds(sr, extra_w, extra_h):
    s, r = sr
    # A virtual desktop that contains the screen, with its own origin.
    vx, vy = s.physical.x - extra_w, s.physical.y - extra_h
    vw, vh = s.physical.w + 2 * extra_w, s.physical.h + 2 * extra_h
    c = crop_box(r, virtual_origin=(vx, vy))
    assert 0 <= c.x and 0 <= c.y and c.x + c.w <= vw and c.y + c.h <= vh
    assert (c.w, c.h) == (r.w, r.h)


@given(st.data())
def test_resize_stays_on_screen(data):
    s, r = data.draw(screen_and_rect())
    handle = data.draw(st.sampled_from([h for h in Handle if h not in (Handle.NONE, Handle.INSIDE)]))
    out = resize(r, handle, data.draw(anywhere(s)), s)
    assert inside(out, s)


@given(st.data())
def test_resize_corner_matches_selection_from_opposite_corner(data):
    s, r = data.draw(screen_and_rect())
    p = data.draw(anywhere(s))
    x0, y0, x1, y1 = r.x, r.y, r.x + r.w, r.y + r.h
    opposite = {Handle.NW: (x1, y1), Handle.NE: (x0, y1), Handle.SW: (x1, y0), Handle.SE: (x0, y0)}
    for handle, fixed in opposite.items():
        assert resize(r, handle, p, s) == selection_rect(s, fixed, p)


@given(st.data())
def test_move_keeps_size_and_screen(data):
    s, r = data.draw(screen_and_rect())
    dx, dy = data.draw(st.integers(-20000, 20000)), data.draw(st.integers(-20000, 20000))
    out = move(r, dx, dy, s)
    assert (out.w, out.h) == (r.w, r.h)
    assert inside(out, s)


@given(st.data())
def test_move_back_restores_when_clear_of_edges(data):
    s, r = data.draw(screen_and_rect())
    p = s.physical
    # FIX-2: draw only offsets that keep the rect on screen (same domain as the old
    # +-3000 draw plus assume, without the filtering that tripped filter_too_much).
    dx = data.draw(st.integers(max(-3000, p.x - r.x), min(3000, p.x + p.w - r.w - r.x)))
    dy = data.draw(st.integers(max(-3000, p.y - r.y), min(3000, p.y + p.h - r.h - r.y)))
    assume(p.x <= r.x + dx and r.x + dx + r.w <= p.x + p.w)
    assume(p.y <= r.y + dy and r.y + dy + r.h <= p.y + p.h)
    assert move(r, dx, dy, s) == Rect(r.x + dx, r.y + dy, r.w, r.h)
    assert move(move(r, dx, dy, s), -dx, -dy, s) == r


@given(st.data())
def test_hit_handle_total(data):
    s, r = data.draw(screen_and_rect())
    h = hit_handle(r, data.draw(anywhere(s)), data.draw(st.integers(0, 20)))
    assert isinstance(h, Handle)


def test_module_uses_stdlib_only():
    import snapocr.geometry as mod

    tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
    imported = {
        (n.module if isinstance(n, ast.ImportFrom) else a.name).split(".")[0]
        for n in ast.walk(tree)
        if isinstance(n, (ast.Import, ast.ImportFrom)) and not (isinstance(n, ast.ImportFrom) and n.level)
        for a in (n.names if isinstance(n, ast.Import) else [n])
    }
    assert imported <= sys.stdlib_module_names
