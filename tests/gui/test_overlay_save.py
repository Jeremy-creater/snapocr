"""M4 WI-23: the save button and Ctrl+S of the capture toolbar, overlay side (PRD F17-1, F17-5; plan D26).

Pinned here:
- The save button, or Ctrl+S, while adjusting emits ``saved(rect)`` (never
  ``selected`` or ``pinned``) and finishes the overlay; ``marks`` keeps the
  marks. Text being typed is kept first (like Enter), also when Ctrl+S is
  pressed inside the text editor.
- Nothing happens while selecting or while a mark is being drawn; an overlay
  without annotation (OCR, translate, code and table OCR) ignores Ctrl+S.
- ``OverlaySession``: a saved overlay ends the session like a confirm, with
  ``action == "save"`` and its marks, set before ``result(rect)``.
"""

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QColor, QImage, QKeyEvent
from PySide6.QtWidgets import QApplication, QToolButton

from snapocr.geometry import Rect, ScreenInfo
from snapocr.gui.overlay import OverlaySession, OverlayState, SelectionOverlay
from support import qt_input as qi

pytestmark = pytest.mark.usefixtures("qapp")

BIG = ScreenInfo("A", Rect(0, 0, 800, 600), 1.0, Rect(0, 0, 800, 600))
AREA = Rect(100, 100, 200, 150)


def frozen() -> QImage:
    image = QImage(800, 600, QImage.Format.Format_RGB32)
    image.fill(QColor(200, 200, 200))
    return image


def recorded(qtbot, annotate=True) -> SelectionOverlay:
    o = SelectionOverlay(frozen(), BIG, annotate=annotate)
    qtbot.addWidget(o)
    o.events = []
    o.selected.connect(lambda r: o.events.append(("selected", r)))
    o.cancelled.connect(lambda: o.events.append(("cancelled", None)))
    o.pinned.connect(lambda r: o.events.append(("pinned", r)))
    if hasattr(o, "saved"):  # the tests then fail on their assertions, not here
        o.saved.connect(lambda r: o.events.append(("saved", r)))
    return o


@pytest.fixture
def overlay(qtbot):
    return recorded(qtbot)


def tb(overlay, name) -> QToolButton:
    found = overlay.toolbar.findChild(QToolButton, name)
    assert found is not None, name
    return found


def ctrl_s(widget) -> None:
    """Ctrl+S as Windows delivers it: the key, the Ctrl modifier and the control character."""
    mod = Qt.KeyboardModifier.ControlModifier
    QApplication.sendEvent(widget, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_S, mod, "\x13"))
    QApplication.sendEvent(widget, QKeyEvent(QEvent.Type.KeyRelease, Qt.Key.Key_S, mod, "\x13"))


def test_save_button_emits_saved_with_the_marks(overlay):
    qi.drag(overlay, 100, 100, 300, 250)
    tb(overlay, "tool-rect").click()
    qi.drag(overlay, 120, 130, 220, 200)
    tb(overlay, "save").click()
    assert overlay.events == [("saved", AREA)]
    assert len(overlay.marks) == 1
    assert overlay.state is OverlayState.FINISHED


def test_ctrl_s_saves_without_marks(overlay):
    qi.drag(overlay, 100, 100, 300, 250)
    ctrl_s(overlay)
    assert overlay.events == [("saved", AREA)]
    assert overlay.marks == ()


def test_plain_s_does_not_save(overlay):
    qi.drag(overlay, 100, 100, 300, 250)
    qi.key(overlay, Qt.Key.Key_S)
    assert overlay.events == []
    assert overlay.state is OverlayState.ADJUSTING


def test_ctrl_s_in_the_text_editor_keeps_the_text_then_saves(overlay):
    qi.drag(overlay, 100, 100, 300, 250)
    tb(overlay, "tool-text").click()
    qi.press(overlay, 150, 150)
    qi.release(overlay, 150, 150)
    overlay.editor.insert("saved text")
    ctrl_s(overlay.editor)
    assert [m.text for m in overlay.marks] == ["saved text"]
    assert overlay.events == [("saved", AREA)]


def test_save_button_keeps_text_being_typed(overlay):
    qi.drag(overlay, 100, 100, 300, 250)
    tb(overlay, "tool-text").click()
    qi.press(overlay, 150, 150)
    qi.release(overlay, 150, 150)
    overlay.editor.insert("typed")
    tb(overlay, "save").click()
    assert [m.text for m in overlay.marks] == ["typed"]
    assert overlay.events == [("saved", AREA)]


def test_ctrl_s_while_selecting_does_nothing(overlay):
    ctrl_s(overlay)
    qi.press(overlay, 100, 100)
    qi.move(overlay, 300, 250)
    ctrl_s(overlay)
    assert overlay.events == []
    assert overlay.state is OverlayState.SELECTING


def test_save_while_drawing_does_nothing(overlay):
    qi.drag(overlay, 100, 100, 300, 250)
    tb(overlay, "tool-rect").click()
    qi.press(overlay, 120, 130)
    qi.move(overlay, 220, 200)
    tb(overlay, "save").click()
    ctrl_s(overlay)
    assert overlay.events == []


def test_ctrl_s_after_finish_does_nothing(overlay):
    qi.drag(overlay, 100, 100, 300, 250)
    ctrl_s(overlay)
    ctrl_s(overlay)
    assert overlay.events == [("saved", AREA)]


def test_overlay_without_annotation_ignores_ctrl_s(qtbot):
    plain = recorded(qtbot, annotate=False)
    qi.drag(plain, 100, 100, 300, 250)
    ctrl_s(plain)
    assert plain.events == []
    assert plain.state is OverlayState.ADJUSTING


def test_session_action_is_save(overlay):
    session = OverlaySession([overlay])
    seen = []
    session.result.connect(lambda rect: seen.append((rect, session.action, session.marks)))
    qi.drag(overlay, 100, 100, 300, 250)
    tb(overlay, "tool-arrow").click()
    qi.drag(overlay, 120, 130, 220, 200)
    tb(overlay, "save").click()
    assert seen == [(AREA, "save", overlay.marks)]
    assert session.finished
