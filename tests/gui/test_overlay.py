"""M2 WI-14: selection overlay and session (PRD F6-1, F6-3, F6-4, F6-5; plan D4).

Pinned here:
- ``SelectionOverlay(frozen, screen)``: ``frozen`` is this screen's part of the
  capture in physical pixels; its size must equal ``screen.physical``'s
  (``ValueError`` otherwise). The widget covers ``screen.logical``; mouse
  positions are mapped with WI-3 ``local_to_physical`` using ``screen.dpr``.
- States: ``SELECTING`` -> (release, >= 4x4) -> ``ADJUSTING`` -> (Enter /
  Return, or double click inside the selection) -> ``selected(Rect)``. A
  release under 4x4 cancels. In ``ADJUSTING``: dragging a handle uses WI-3
  ``resize`` from the rect at press time, dragging the inside uses ``move``,
  a press outside starts a new selection. Esc or a right press cancels in any
  state; confirming a rect under 4x4 cancels. After the result the overlay is
  ``FINISHED`` and ignores all input.
- Enter in ``SELECTING`` does nothing.
- Cursor: cross while selecting and outside the selection; size-all inside;
  diagonal / vertical / horizontal resize cursors on handles.
- Painting: the whole frozen image dimmed; inside the selection undimmed.
  Border and handles stay within ``HANDLE_MARGIN`` logical px of the edges.
- ``OverlaySession(overlays)``: the first ``selected`` / ``cancelled`` of any
  overlay closes all of them and emits ``result`` once, with the ``Rect`` or
  ``None``. ``start()`` shows each overlay at its screen's logical geometry.
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QImage

from snapocr.geometry import Handle, Rect, ScreenInfo, is_cancel_size, local_to_physical, move, resize, selection_rect
from snapocr.gui.overlay import HANDLE_MARGIN, OverlaySession, OverlayState, SelectionOverlay
from support import qt_input as qi
from support.qimages import gradient, pixels

pytestmark = pytest.mark.usefixtures("qapp")

ONE = ScreenInfo("A", Rect(0, 0, 200, 150), 1.0, Rect(0, 0, 200, 150))
SIDE = ScreenInfo("B", Rect(-1707, 0, 1707, 960), 1.5, Rect(-2560, 0, 2560, 1440))


def bright(w: int, h: int) -> QImage:
    """A frozen image with no black pixels, so dimming is always visible."""
    image = gradient(w, h)
    image.invertPixels()  # keeps distinct pixels; the gradient's (0,0,0) becomes white
    return image


def frozen_for(screen: ScreenInfo) -> QImage:
    p = screen.physical
    return bright(p.w, p.h) if p.w * p.h <= 40_000 else QImage(p.w, p.h, QImage.Format.Format_RGB32)


class Probe:
    def __init__(self, overlay: SelectionOverlay):
        self.selected: list[Rect] = []
        self.cancelled = 0
        overlay.selected.connect(self.selected.append)
        overlay.cancelled.connect(self._cancel)

    def _cancel(self):
        self.cancelled += 1


@pytest.fixture
def make(qtbot):
    def factory(screen=ONE, frozen=None):
        overlay = SelectionOverlay(frozen if frozen is not None else frozen_for(screen), screen)
        qtbot.addWidget(overlay)
        return overlay, Probe(overlay)

    return factory


def phys(screen, x, y):
    return local_to_physical(screen, x, y)


# --- construction ---------------------------------------------------------


def test_frozen_size_must_match_physical_screen():
    with pytest.raises(ValueError, match="frozen"):
        SelectionOverlay(bright(199, 150), ONE)


def test_initial_state(make):
    overlay, probe = make()
    assert overlay.state is OverlayState.SELECTING
    assert overlay.selection is None
    assert overlay.cursor().shape() == Qt.CursorShape.CrossCursor
    assert (overlay.width(), overlay.height()) == (200, 150)
    assert overlay.hasMouseTracking()


# --- F6-1 painting ----------------------------------------------------------


def _darker(out: int, src: int) -> bool:
    o = [(out >> s) & 0xFF for s in (16, 8, 0)]
    r = [(src >> s) & 0xFF for s in (16, 8, 0)]
    return all(a <= b for a, b in zip(o, r)) and sum(o) < sum(r)


def test_whole_screen_is_dimmed_before_selecting(make):
    overlay, _ = make()
    src, out = pixels(frozen_for(ONE)), pixels(overlay.grab().toImage())
    assert all(_darker(out[y][x], src[y][x]) for y in range(0, 150, 7) for x in range(0, 200, 7))


def test_selection_is_undimmed_and_the_rest_dimmed(make):
    overlay, _ = make()
    qi.drag(overlay, 40, 30, 160, 120)
    assert overlay.state is OverlayState.ADJUSTING
    src, out = pixels(frozen_for(ONE)), pixels(overlay.grab().toImage())
    m = HANDLE_MARGIN
    label = overlay.size_label[1]  # M5 WI-6 (F18-6): the size label sits in the dimmed part, above
    assert label.bottom() < 30
    for y in range(150):
        for x in range(200):
            inner = 40 + m <= x < 160 - m and 30 + m <= y < 120 - m
            outer = x < 40 - m or x >= 160 + m or y < 30 - m or y >= 120 + m
            if label.contains(x, y):
                continue
            if inner:
                assert out[y][x] == src[y][x], (x, y)
            elif outer:
                assert _darker(out[y][x], src[y][x]), (x, y)


# --- coordinates and confirmation ------------------------------------------------


def test_drag_on_scaled_side_screen_matches_wi3(make):
    overlay, probe = make(SIDE)
    qi.drag(overlay, 100, 100, 200, 150)
    assert probe.selected == []  # release alone never selects (F6-5)
    assert overlay.selection == Rect(-2410, 150, 150, 75)
    qi.key(overlay, Qt.Key.Key_Return)
    assert probe.selected == [Rect(-2410, 150, 150, 75)]
    assert probe.cancelled == 0
    assert overlay.state is OverlayState.FINISHED


@pytest.mark.parametrize("k", [Qt.Key.Key_Return, Qt.Key.Key_Enter])
def test_enter_confirms(make, k):
    overlay, probe = make()
    qi.drag(overlay, 10, 10, 50, 40)
    qi.key(overlay, k)
    assert probe.selected == [Rect(10, 10, 40, 30)]


def test_double_click_inside_confirms(make):
    overlay, probe = make()
    qi.drag(overlay, 10, 10, 90, 70)
    qi.press(overlay, 50, 40)
    qi.release(overlay, 50, 40)
    qi.double_click(overlay, 50, 40)
    assert probe.selected == [Rect(10, 10, 80, 60)]


def test_reverse_drag_gives_same_rect(make):
    a, pa = make()
    b, pb = make()
    qi.drag(a, 30, 20, 130, 90)
    qi.drag(b, 130, 90, 30, 20)
    assert a.selection == b.selection == Rect(30, 20, 100, 70)


def test_drag_past_the_screen_edge_is_clipped(make):
    overlay, _ = make()
    qi.drag(overlay, 150, 100, 400, -50)
    assert overlay.selection == Rect(150, 0, 50, 100)


def test_enter_while_selecting_does_nothing(make):
    overlay, probe = make()
    qi.key(overlay, Qt.Key.Key_Return)
    qi.press(overlay, 10, 10)
    qi.move(overlay, 60, 60)
    qi.key(overlay, Qt.Key.Key_Return)  # still dragging
    assert probe.selected == [] and probe.cancelled == 0
    assert overlay.state is OverlayState.SELECTING


# --- F6-3 cancel paths -------------------------------------------------------------


@pytest.mark.parametrize("end", [(13, 13), (13, 100), (100, 13), (10, 10)], ids=["3x3", "3x90", "90x3", "click"])
def test_small_release_cancels(make, end):
    overlay, probe = make()
    qi.drag(overlay, 10, 10, *end)
    assert probe.cancelled == 1 and probe.selected == []
    assert overlay.state is OverlayState.FINISHED


def test_four_by_four_is_kept(make):
    overlay, probe = make()
    qi.drag(overlay, 10, 10, 14, 14)
    assert overlay.state is OverlayState.ADJUSTING
    assert overlay.selection == Rect(10, 10, 4, 4)


@pytest.mark.parametrize("state", ["selecting", "dragging", "adjusting"])
@pytest.mark.parametrize("how", ["esc", "right"])
def test_esc_or_right_press_cancels_in_any_state(make, state, how):
    overlay, probe = make()
    if state == "dragging":
        qi.press(overlay, 10, 10)
        qi.move(overlay, 80, 80)
    elif state == "adjusting":
        qi.drag(overlay, 10, 10, 80, 80)
    if how == "esc":
        qi.key(overlay, Qt.Key.Key_Escape)
    else:
        qi.press(overlay, 50, 50, qi.RIGHT)
    assert probe.cancelled == 1 and probe.selected == []
    assert overlay.state is OverlayState.FINISHED


def test_confirming_a_rect_shrunk_below_4x4_cancels(make):
    overlay, probe = make()
    qi.drag(overlay, 10, 10, 80, 80)
    qi.drag(overlay, 80, 80, 12, 79)  # SE handle to just right of the left edge
    assert overlay.selection == Rect(10, 10, 2, 69)
    qi.key(overlay, Qt.Key.Key_Return)
    assert probe.cancelled == 1 and probe.selected == []


def test_input_after_the_result_is_ignored(make):
    overlay, probe = make()
    qi.drag(overlay, 10, 10, 80, 80)
    qi.key(overlay, Qt.Key.Key_Return)
    qi.key(overlay, Qt.Key.Key_Return)
    qi.key(overlay, Qt.Key.Key_Escape)
    qi.drag(overlay, 20, 20, 90, 90)
    qi.press(overlay, 5, 5, qi.RIGHT)
    assert probe.selected == [Rect(10, 10, 70, 70)]
    assert probe.cancelled == 0
    assert overlay.selection == Rect(10, 10, 70, 70)


# --- F6-5 adjusting -----------------------------------------------------------------


def test_drag_se_handle_resizes_like_wi3(make):
    overlay, probe = make(SIDE)
    qi.drag(overlay, 100, 100, 200, 150)
    start = overlay.selection
    qi.drag(overlay, 200, 150, 260.4, 190.2)
    assert overlay.selection == resize(start, Handle.SE, phys(SIDE, 260.4, 190.2), SIDE)
    qi.key(overlay, Qt.Key.Key_Return)
    assert probe.selected == [overlay.selection]


def test_drag_handle_past_opposite_edge_flips(make):
    overlay, _ = make()
    qi.drag(overlay, 50, 50, 100, 100)
    qi.drag(overlay, 100, 75, 20, 75)  # E handle to the left of the W edge
    assert overlay.selection == Rect(20, 50, 30, 50)


def test_drag_inside_moves_like_wi3(make):
    overlay, _ = make(SIDE)
    qi.drag(overlay, 100, 100, 200, 150)
    start = overlay.selection
    qi.drag(overlay, 150, 125, 170.5, 100)
    p0, p1 = phys(SIDE, 150, 125), phys(SIDE, 170.5, 100)
    assert overlay.selection == move(start, p1[0] - p0[0], p1[1] - p0[1], SIDE)
    assert (overlay.selection.w, overlay.selection.h) == (start.w, start.h)


def test_move_stops_at_screen_edge(make):
    overlay, _ = make()
    qi.drag(overlay, 50, 50, 100, 100)
    qi.drag(overlay, 75, 75, -500, 75)
    assert overlay.selection == Rect(0, 50, 50, 50)


def test_press_outside_starts_a_new_selection(make):
    overlay, probe = make(SIDE)
    qi.drag(overlay, 100, 100, 200, 150)
    qi.drag(overlay, 400, 300, 300, 250)
    assert overlay.selection == selection_rect(SIDE, phys(SIDE, 400, 300), phys(SIDE, 300, 250))
    assert overlay.state is OverlayState.ADJUSTING
    qi.key(overlay, Qt.Key.Key_Return)
    assert probe.selected == [overlay.selection]


def test_click_outside_without_drag_cancels(make):
    overlay, probe = make()
    qi.drag(overlay, 50, 50, 100, 100)
    qi.press(overlay, 150, 120)
    qi.release(overlay, 150, 120)
    assert probe.cancelled == 1 and probe.selected == []


@pytest.mark.parametrize(
    "point, shape",
    [
        ((75, 75), Qt.CursorShape.SizeAllCursor),
        ((100, 100), Qt.CursorShape.SizeFDiagCursor),
        ((50, 50), Qt.CursorShape.SizeFDiagCursor),
        ((100, 50), Qt.CursorShape.SizeBDiagCursor),
        ((50, 100), Qt.CursorShape.SizeBDiagCursor),
        ((100, 75), Qt.CursorShape.SizeHorCursor),
        ((50, 75), Qt.CursorShape.SizeHorCursor),
        ((75, 50), Qt.CursorShape.SizeVerCursor),
        ((75, 100), Qt.CursorShape.SizeVerCursor),
        ((150, 130), Qt.CursorShape.CrossCursor),
    ],
    ids=["inside", "se", "nw", "ne", "sw", "e", "w", "n", "s", "outside"],
)
def test_hover_cursor_follows_hit_handle(make, point, shape):
    overlay, _ = make()
    qi.drag(overlay, 50, 50, 100, 100)
    qi.move(overlay, *point, buttons=qi.NONE)
    assert overlay.cursor().shape() == shape


def test_hover_before_any_press_changes_nothing(make):
    """Pins the hover-while-selecting branch, which the random action test only sometimes reaches."""
    overlay, probe = make()
    qi.move(overlay, 60, 60, buttons=qi.NONE)
    assert overlay.state is OverlayState.SELECTING
    assert overlay.selection is None
    assert overlay.cursor().shape() == Qt.CursorShape.CrossCursor
    assert (probe.selected, probe.cancelled) == ([], 0)


def test_cursor_is_cross_while_dragging_a_new_selection(make):
    overlay, _ = make()
    qi.press(overlay, 10, 10)
    qi.move(overlay, 60, 60)
    assert overlay.cursor().shape() == Qt.CursorShape.CrossCursor


# --- session --------------------------------------------------------------------------


@pytest.fixture
def session_of(qtbot):
    def factory(*screens):
        overlays = [SelectionOverlay(frozen_for(s), s) for s in screens]
        for o in overlays:
            qtbot.addWidget(o)
        session = OverlaySession(overlays)
        results = []
        session.result.connect(results.append)
        session.start()
        return session, overlays, results

    return factory


SMALL_B = ScreenInfo("B", Rect(200, 0, 160, 120), 1.0, Rect(200, 0, 160, 120))


def test_session_shows_each_overlay_at_its_logical_geometry(session_of):
    _, (a, b), _ = session_of(ONE, SMALL_B)
    assert a.isVisible() and b.isVisible()
    assert a.geometry() == QRect(0, 0, 200, 150)
    assert b.geometry() == QRect(200, 0, 160, 120)


def test_selecting_on_one_overlay_closes_all_and_reports_once(session_of):
    session, (a, b), results = session_of(ONE, SMALL_B)
    qi.drag(a, 10, 10, 60, 60)
    assert b.isVisible()
    qi.key(a, Qt.Key.Key_Return)
    assert results == [Rect(10, 10, 50, 50)]
    assert not a.isVisible() and not b.isVisible()
    assert session.finished
    qi.key(b, Qt.Key.Key_Escape)
    qi.drag(b, 10, 10, 60, 60)
    qi.key(b, Qt.Key.Key_Return)
    assert results == [Rect(10, 10, 50, 50)]


def test_cancel_on_other_overlay_reports_none_once(session_of):
    session, (a, b), results = session_of(ONE, SMALL_B)
    qi.drag(a, 10, 10, 60, 60)
    qi.key(b, Qt.Key.Key_Escape)
    assert results == [None]
    assert not a.isVisible() and not b.isVisible()
    qi.key(a, Qt.Key.Key_Return)
    assert results == [None]


def test_session_rejects_empty_overlay_list():
    with pytest.raises(ValueError):
        OverlaySession([])


def test_start_twice_is_rejected(session_of):
    session, _, _ = session_of(ONE)
    with pytest.raises(RuntimeError):
        session.start()


# --- properties ----------------------------------------------------------------------

ACTIONS = st.one_of(
    st.tuples(st.just("press"), st.integers(0, 1), st.floats(-20, 220), st.floats(-20, 170)),
    st.tuples(st.just("move"), st.integers(0, 1), st.floats(-20, 220), st.floats(-20, 170)),
    st.tuples(st.just("release"), st.integers(0, 1), st.floats(-20, 220), st.floats(-20, 170)),
    st.tuples(st.just("dbl"), st.integers(0, 1), st.floats(0, 200), st.floats(0, 150)),
    st.tuples(st.just("enter"), st.integers(0, 1), st.just(0.0), st.just(0.0)),
    st.tuples(st.just("esc"), st.integers(0, 1), st.just(0.0), st.just(0.0)),
    st.tuples(st.just("right"), st.integers(0, 1), st.floats(0, 200), st.floats(0, 150)),
)
PROP_SCREENS = [
    ScreenInfo("A", Rect(0, 0, 200, 150), 1.0, Rect(0, 0, 200, 150)),
    ScreenInfo("B", Rect(200, 0, 134, 100), 1.5, Rect(300, 0, 200, 150)),
]


@settings(max_examples=30, deadline=None)
@given(st.lists(ACTIONS, max_size=25))
def test_session_ends_with_exactly_one_result_inside_its_screen(qapp, actions):
    overlays = [SelectionOverlay(frozen_for(s), s) for s in PROP_SCREENS]
    session = OverlaySession(overlays)
    results, origins = [], []
    session.result.connect(results.append)
    for i, o in enumerate(overlays):
        o.selected.connect(lambda r, i=i: origins.append(i))
    session.start()
    try:
        for kind, i, x, y in actions:
            o = overlays[i]
            if kind == "press":
                qi.press(o, x, y)
            elif kind == "move":
                qi.move(o, x, y)
            elif kind == "release":
                qi.release(o, x, y)
            elif kind == "dbl":
                qi.double_click(o, x, y)
            elif kind == "enter":
                qi.key(o, Qt.Key.Key_Return)
            elif kind == "esc":
                qi.key(o, Qt.Key.Key_Escape)
            else:
                qi.press(o, x, y, qi.RIGHT)
        qi.key(overlays[0], Qt.Key.Key_Escape)  # end an unfinished session
        qi.key(overlays[1], Qt.Key.Key_Escape)
        assert len(results) == 1
        assert session.finished
        assert not any(o.isVisible() for o in overlays)
        rect = results[0]
        if rect is not None:
            assert origins and len(origins) == 1
            p = PROP_SCREENS[origins[0]].physical
            assert p.x <= rect.x and p.y <= rect.y and rect.x + rect.w <= p.x + p.w and rect.y + rect.h <= p.y + p.h
            assert not is_cancel_size(rect)
    finally:
        for o in overlays:
            o.deleteLater()


@settings(max_examples=30, deadline=None)
@given(st.floats(0, 200), st.floats(0, 150), st.floats(0, 200), st.floats(0, 150))
def test_drag_direction_does_not_matter(qapp, x0, y0, x1, y1):
    a, b = SelectionOverlay(frozen_for(ONE), ONE), SelectionOverlay(frozen_for(ONE), ONE)
    try:
        qi.drag(a, x0, y0, x1, y1)
        qi.drag(b, x1, y1, x0, y0)
        assert a.selection == b.selection
        assert a.state is b.state
    finally:
        a.deleteLater()
        b.deleteLater()


# --- added after the first green (coverage) ------------------------------------------


def test_middle_button_is_ignored(make):
    overlay, probe = make()
    qi.press(overlay, 10, 10, Qt.MouseButton.MiddleButton)
    qi.release(overlay, 10, 10, Qt.MouseButton.MiddleButton)
    assert overlay.state is OverlayState.SELECTING and overlay.selection is None
    qi.drag(overlay, 10, 10, 60, 60)
    qi.press(overlay, 30, 30, Qt.MouseButton.MiddleButton)
    assert overlay.state is OverlayState.ADJUSTING
    assert probe.selected == [] and probe.cancelled == 0


def test_double_click_on_a_handle_does_not_confirm(make):
    overlay, probe = make()
    qi.drag(overlay, 10, 10, 60, 60)
    qi.press(overlay, 60, 60)
    qi.release(overlay, 60, 60)
    qi.double_click(overlay, 60, 60)
    assert probe.selected == [] and probe.cancelled == 0
    assert overlay.state is OverlayState.ADJUSTING


def test_other_keys_do_nothing(make):
    overlay, probe = make()
    qi.drag(overlay, 10, 10, 60, 60)
    qi.key(overlay, Qt.Key.Key_A)
    qi.key(overlay, Qt.Key.Key_Space)
    assert overlay.state is OverlayState.ADJUSTING
    assert probe.selected == [] and probe.cancelled == 0


def test_handles_are_drawn_only_while_adjusting(make):
    overlay, _ = make()
    src = pixels(frozen_for(ONE))
    qi.press(overlay, 40, 30)
    qi.move(overlay, 160, 120)
    during = pixels(overlay.grab().toImage())
    qi.release(overlay, 160, 120)
    after = pixels(overlay.grab().toImage())
    # (37, 27): outside the NW corner, inside the NW handle square
    assert _darker(during[27][37], src[27][37])
    assert after[27][37] == 0xFF000000 | 0x1E90FF
