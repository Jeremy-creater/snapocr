"""M4 WI-4: annotation mode of the selection overlay (PRD F14-1 to F14-3, F14-6, F14-7; plan D10 to D12).

Pinned here:
- ``SelectionOverlay(..., annotate=False)`` (the default) has no toolbar
  (``overlay.toolbar is None``) and behaves exactly as in M2.
- ``annotate=True``: ``overlay.toolbar`` is an ``AnnotateToolbar`` with the
  given style; hidden while selecting, shown at ``toolbar_place(selection in
  local logical px rounded outwards, sizeHint, whole overlay, TOOLBAR_GAP)``
  whenever the selection is being adjusted, and moved with it.
- F14-3: with no tool picked and no marks the mouse adjusts the selection as
  before. With a tool picked or a mark drawn the selection is fixed: presses
  outside it do nothing, and handles are not drawn.
- With a drag tool picked, a left drag that starts inside the selection draws
  ``drag_mark(tool, press, release, toolbar.style, dpr)`` (physical px); the
  draft is visible while dragging; ``None`` (too short) adds nothing.
- Undo (Ctrl+Z or the toolbar) drops the last mark; the toolbar's undo button
  is enabled exactly when there is something to undo.
- Confirm: Enter, the toolbar's done button, or a double click inside while no
  tool is picked -> ``selected(rect)``; ``overlay.marks`` keeps the marks.
  With a tool picked a double click does not confirm. Enter in the middle of a
  drawing drag does nothing. The toolbar's cancel button cancels.
- ``style_changed(Style)`` repeats the toolbar's.
- ``OverlaySession``: ``marks`` is the confirmed overlay's marks, ``action`` is
  ``"copy"``; both are set before ``result`` is emitted.
"""

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QColor, QImage, QKeyEvent
from PySide6.QtWidgets import QApplication, QToolButton

from snapocr.annotate import DEFAULT_STYLE, PALETTE, Mark, Style, Tool, drag_mark, scaled, toolbar_place
from snapocr.geometry import Rect, ScreenInfo, local_to_physical
from snapocr.gui.annotate_toolbar import AnnotateToolbar
from snapocr.gui.overlay import TOOLBAR_GAP, OverlaySession, OverlayState, SelectionOverlay
from support import qt_input as qi

pytestmark = pytest.mark.usefixtures("qapp")

BIG = ScreenInfo("A", Rect(0, 0, 800, 600), 1.0, Rect(0, 0, 800, 600))
HI = ScreenInfo("B", Rect(800, 0, 400, 300), 2.0, Rect(1600, 0, 800, 600))
GREY = QColor(200, 200, 200)


def frozen(screen: ScreenInfo) -> QImage:
    image = QImage(screen.physical.w, screen.physical.h, QImage.Format.Format_RGB32)
    image.fill(GREY)
    return image


class Probe:
    def __init__(self, overlay: SelectionOverlay):
        self.selected: list[Rect] = []
        self.cancelled = 0
        self.styles: list[Style] = []
        overlay.selected.connect(self.selected.append)
        overlay.cancelled.connect(self._cancel)
        overlay.style_changed.connect(self.styles.append)

    def _cancel(self):
        self.cancelled += 1


@pytest.fixture
def make(qtbot):
    def factory(screen=BIG, **kw):
        overlay = SelectionOverlay(frozen(screen), screen, **kw)
        qtbot.addWidget(overlay)
        return overlay, Probe(overlay)

    return factory


def tb(overlay: SelectionOverlay, name: str) -> QToolButton:
    assert overlay.toolbar is not None, "no toolbar"
    found = overlay.toolbar.findChild(QToolButton, name)
    assert found is not None, name
    return found


def ctrl_z(widget):
    QApplication.sendEvent(widget, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier))


def toolbar_shown(overlay: SelectionOverlay) -> bool:
    return overlay.toolbar is not None and overlay.toolbar.isVisibleTo(overlay)


def selected_with_rect_tool(make, screen=BIG, **kw):
    overlay, probe = make(screen, annotate=True, **kw)
    qi.drag(overlay, 100, 100, 300, 250)
    tb(overlay, "tool-rect").click()
    return overlay, probe


# --- no annotation --------------------------------------------------------------


def test_no_toolbar_by_default(make):
    overlay, _ = make()
    qi.drag(overlay, 100, 100, 300, 250)
    assert overlay.toolbar is None
    assert overlay.marks == ()


# --- toolbar placement --------------------------------------------------------


def test_toolbar_starts_hidden_with_the_given_style(make):
    overlay, _ = make(annotate=True, style=Style(PALETTE[5], 2))
    assert isinstance(overlay.toolbar, AnnotateToolbar)
    assert overlay.toolbar.style == Style(PALETTE[5], 2)
    assert not toolbar_shown(overlay)


def test_toolbar_appears_below_the_adjusted_selection(make):
    overlay, _ = make(annotate=True)
    qi.drag(overlay, 100, 100, 300, 250)
    assert toolbar_shown(overlay)
    hint = overlay.toolbar.sizeHint()
    x, y = toolbar_place(Rect(100, 100, 200, 150), (hint.width(), hint.height()), Rect(0, 0, 800, 600), TOOLBAR_GAP)
    assert (overlay.toolbar.x(), overlay.toolbar.y()) == (x, y)
    assert overlay.toolbar.y() >= 250


def test_toolbar_on_a_scaled_screen_uses_logical_coordinates(make):
    overlay, _ = make(HI, annotate=True)
    qi.drag(overlay, 50, 40, 150, 120)
    hint = overlay.toolbar.sizeHint()
    x, y = toolbar_place(Rect(50, 40, 100, 80), (hint.width(), hint.height()), Rect(0, 0, 400, 300), TOOLBAR_GAP)
    assert (overlay.toolbar.x(), overlay.toolbar.y()) == (x, y)


def test_toolbar_follows_a_moved_selection(make):
    overlay, _ = make(annotate=True)
    qi.drag(overlay, 100, 100, 300, 250)
    qi.drag(overlay, 200, 150, 250, 100)  # move by (50, -50)
    assert overlay.selection == Rect(150, 50, 200, 150)
    hint = overlay.toolbar.sizeHint()
    x, y = toolbar_place(Rect(150, 50, 200, 150), (hint.width(), hint.height()), Rect(0, 0, 800, 600), TOOLBAR_GAP)
    assert (overlay.toolbar.x(), overlay.toolbar.y()) == (x, y)


def test_toolbar_hides_while_selecting_again(make):
    overlay, _ = make(annotate=True)
    qi.drag(overlay, 100, 100, 300, 250)
    qi.press(overlay, 500, 400)
    qi.move(overlay, 600, 500)
    assert overlay.state is OverlayState.SELECTING
    assert not toolbar_shown(overlay)
    qi.release(overlay, 600, 500)
    assert toolbar_shown(overlay)


# --- drawing --------------------------------------------------------------------


def test_drag_inside_draws_a_rectangle(make):
    overlay, probe = selected_with_rect_tool(make)
    qi.drag(overlay, 220, 200, 120, 130)
    assert overlay.marks == (Mark(Tool.RECT, ((120, 130), (220, 200)), PALETTE[0], 4),)
    assert overlay.selection == Rect(100, 100, 200, 150)
    assert overlay.state is OverlayState.ADJUSTING
    assert probe.selected == [] and probe.cancelled == 0


@pytest.mark.parametrize(("name", "tool"), [("tool-ellipse", Tool.ELLIPSE), ("tool-arrow", Tool.ARROW)])
def test_other_drag_tools(make, name, tool):
    overlay, _ = make(annotate=True)
    qi.drag(overlay, 100, 100, 300, 250)
    tb(overlay, name).click()
    qi.drag(overlay, 150, 220, 250, 120)
    assert overlay.marks == (drag_mark(tool, (150, 220), (250, 120), DEFAULT_STYLE, 1.0),)


def test_marks_on_a_scaled_screen_are_physical(make):
    overlay, _ = make(HI, annotate=True)
    qi.drag(overlay, 50, 40, 150, 120)
    tb(overlay, "tool-arrow").click()
    qi.drag(overlay, 60, 50, 100, 90)
    start, end = local_to_physical(HI, 60, 50), local_to_physical(HI, 100, 90)
    assert overlay.marks == (Mark(Tool.ARROW, (start, end), PALETTE[0], scaled(4, 2.0)),)
    assert overlay.marks[0].size == 8


def test_style_from_the_toolbar_is_used_and_reported(make):
    overlay, probe = selected_with_rect_tool(make)
    tb(overlay, "color-4").click()
    tb(overlay, "level-2").click()
    qi.drag(overlay, 120, 130, 220, 200)
    assert overlay.marks[0].color == PALETTE[4] and overlay.marks[0].size == 6
    assert probe.styles == [Style(PALETTE[4], 1), Style(PALETTE[4], 2)]


def test_short_drag_draws_nothing(make):
    overlay, _ = selected_with_rect_tool(make)
    qi.drag(overlay, 150, 150, 152, 151)
    assert overlay.marks == ()


def test_drag_starting_outside_the_selection_draws_nothing(make):
    overlay, _ = selected_with_rect_tool(make)
    qi.drag(overlay, 50, 50, 200, 200)
    assert overlay.marks == ()
    assert overlay.selection == Rect(100, 100, 200, 150)
    assert overlay.state is OverlayState.ADJUSTING


def test_marks_may_run_past_the_selection(make):
    overlay, _ = selected_with_rect_tool(make)
    qi.drag(overlay, 250, 200, 400, 300)
    assert overlay.marks == (Mark(Tool.RECT, ((250, 200), (400, 300)), PALETTE[0], 4),)


def test_draft_is_painted_while_dragging(make):
    overlay, _ = selected_with_rect_tool(make)
    qi.press(overlay, 120, 130)
    qi.move(overlay, 220, 200)
    assert overlay.marks == ()
    image = overlay.grab().toImage()
    assert image.pixelColor(120, 160) == QColor(PALETTE[0])
    assert image.pixelColor(170, 165) == GREY


def test_finished_marks_are_painted_and_clipped_to_the_selection(make):
    overlay, _ = selected_with_rect_tool(make)
    qi.drag(overlay, 150, 150, 400, 400)
    image = overlay.grab().toImage()
    assert image.pixelColor(150, 200) == QColor(PALETTE[0])
    assert image.pixelColor(200, 150) == QColor(PALETTE[0])
    assert image.pixelColor(150, 320) != QColor(PALETTE[0])  # below the selection: cut off


# --- F14-3 locking -------------------------------------------------------------------


def test_picked_tool_locks_the_selection(make):
    overlay, _ = selected_with_rect_tool(make)
    qi.drag(overlay, 300, 250, 400, 400)  # the SE handle: would resize
    assert overlay.selection == Rect(100, 100, 200, 150)
    qi.drag(overlay, 500, 500, 600, 580)  # outside: would start a new selection
    assert overlay.selection == Rect(100, 100, 200, 150)
    assert overlay.state is OverlayState.ADJUSTING


def test_dropping_the_tool_without_marks_unlocks(make):
    overlay, _ = selected_with_rect_tool(make)
    tb(overlay, "tool-rect").click()
    qi.drag(overlay, 200, 150, 250, 100)
    assert overlay.selection == Rect(150, 50, 200, 150)


def test_marks_keep_the_selection_locked_without_a_tool(make):
    overlay, _ = selected_with_rect_tool(make)
    qi.drag(overlay, 120, 130, 220, 200)
    tb(overlay, "tool-rect").click()
    qi.drag(overlay, 200, 150, 250, 100)  # inside: would move
    qi.drag(overlay, 500, 500, 600, 580)  # outside: would reselect
    assert overlay.selection == Rect(100, 100, 200, 150)
    assert len(overlay.marks) == 1


def test_handles_are_not_drawn_when_locked(make):
    overlay, _ = make(annotate=True)
    qi.drag(overlay, 100, 100, 300, 250)
    before = overlay.grab().toImage()
    tb(overlay, "tool-rect").click()
    after = overlay.grab().toImage()
    assert before.pixelColor(200, 102) != GREY  # inside the N handle
    assert after.pixelColor(200, 102) == GREY  # the handle is gone


# --- undo -------------------------------------------------------------------------------


def test_ctrl_z_and_undo_button(make):
    overlay, _ = selected_with_rect_tool(make)
    assert not tb(overlay, "undo").isEnabled()
    qi.drag(overlay, 120, 130, 220, 200)
    qi.drag(overlay, 130, 140, 230, 210)
    assert len(overlay.marks) == 2 and tb(overlay, "undo").isEnabled()
    ctrl_z(overlay)
    assert len(overlay.marks) == 1 and tb(overlay, "undo").isEnabled()
    tb(overlay, "undo").click()
    assert overlay.marks == () and not tb(overlay, "undo").isEnabled()
    ctrl_z(overlay)
    assert overlay.marks == ()


def test_ctrl_z_without_annotation_does_nothing(make):
    overlay, probe = make()
    qi.drag(overlay, 100, 100, 300, 250)
    ctrl_z(overlay)
    assert overlay.state is OverlayState.ADJUSTING and probe.cancelled == 0


# --- confirm and cancel ---------------------------------------------------------------


@pytest.mark.parametrize("how", ["enter", "done"])
def test_confirm_keeps_the_marks(make, how):
    overlay, probe = selected_with_rect_tool(make)
    qi.drag(overlay, 120, 130, 220, 200)
    if how == "enter":
        qi.key(overlay, Qt.Key.Key_Return)
    else:
        tb(overlay, "done").click()
    assert probe.selected == [Rect(100, 100, 200, 150)]
    assert overlay.marks == (Mark(Tool.RECT, ((120, 130), (220, 200)), PALETTE[0], 4),)
    assert overlay.state is OverlayState.FINISHED


def test_cancel_button(make):
    overlay, probe = selected_with_rect_tool(make)
    tb(overlay, "cancel").click()
    assert probe.cancelled == 1 and probe.selected == []


def test_double_click_with_a_tool_does_not_confirm(make):
    overlay, probe = selected_with_rect_tool(make)
    qi.press(overlay, 200, 180)
    qi.release(overlay, 200, 180)
    qi.double_click(overlay, 200, 180)
    assert probe.selected == [] and overlay.marks == ()


def test_double_click_without_a_tool_confirms_with_marks(make):
    overlay, probe = selected_with_rect_tool(make)
    qi.drag(overlay, 120, 130, 220, 200)
    tb(overlay, "tool-rect").click()
    qi.press(overlay, 200, 180)
    qi.release(overlay, 200, 180)
    qi.double_click(overlay, 200, 180)
    assert probe.selected == [Rect(100, 100, 200, 150)] and len(overlay.marks) == 1


def test_enter_while_drawing_does_nothing(make):
    overlay, probe = selected_with_rect_tool(make)
    qi.press(overlay, 120, 130)
    qi.move(overlay, 220, 200)
    qi.key(overlay, Qt.Key.Key_Return)
    assert probe.selected == []
    qi.release(overlay, 220, 200)
    assert len(overlay.marks) == 1


def test_escape_still_cancels(make):
    overlay, probe = selected_with_rect_tool(make)
    qi.drag(overlay, 120, 130, 220, 200)
    qi.key(overlay, Qt.Key.Key_Escape)
    assert probe.cancelled == 1


# --- session ---------------------------------------------------------------------------


def test_session_records_marks_before_the_result(make):
    a, _ = make(annotate=True)
    b, _ = make(HI, annotate=True)
    session = OverlaySession([a, b])
    seen = []
    session.result.connect(lambda rect: seen.append((rect, session.marks, session.action)))
    qi.drag(b, 50, 40, 150, 120)
    tb(b, "tool-rect").click()
    qi.drag(b, 60, 50, 100, 90)
    qi.key(b, Qt.Key.Key_Return)
    assert len(seen) == 1
    rect, marks, action = seen[0]
    assert rect == b.selection and marks == b.marks and len(marks) == 1 and action == "copy"


def test_cancelled_session_has_no_marks(make):
    a, _ = make(annotate=True)
    session = OverlaySession([a])
    seen = []
    session.result.connect(lambda rect: seen.append((rect, session.marks)))
    qi.drag(a, 100, 100, 300, 250)
    tb(a, "tool-rect").click()
    qi.drag(a, 120, 130, 220, 200)
    qi.key(a, Qt.Key.Key_Escape)
    assert seen == [(None, ())]
