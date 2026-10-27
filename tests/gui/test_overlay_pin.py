"""M4 WI-8: the pin button of the capture toolbar, overlay side (PRD F15-1; plan D10).

Pinned here:
- In annotation mode the toolbar shows its pin button.
- Clicking it while adjusting emits ``pinned(rect)`` (never ``selected``) and
  finishes the overlay; ``marks`` keeps the marks; text being typed is kept
  first.
- ``OverlaySession``: a pinned overlay ends the session like a confirm, with
  ``action == "pin"`` and its marks, set before ``result(rect)``.
"""

import pytest
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QToolButton

from snapocr.geometry import Rect, ScreenInfo
from snapocr.gui.overlay import OverlaySession, OverlayState, SelectionOverlay
from support import qt_input as qi

pytestmark = pytest.mark.usefixtures("qapp")

BIG = ScreenInfo("A", Rect(0, 0, 800, 600), 1.0, Rect(0, 0, 800, 600))


def frozen() -> QImage:
    image = QImage(800, 600, QImage.Format.Format_RGB32)
    image.fill(QColor(200, 200, 200))
    return image


@pytest.fixture
def overlay(qtbot):
    o = SelectionOverlay(frozen(), BIG, annotate=True)
    qtbot.addWidget(o)
    o.events = []
    o.selected.connect(lambda r: o.events.append(("selected", r)))
    o.cancelled.connect(lambda: o.events.append(("cancelled", None)))
    if hasattr(o, "pinned"):  # the tests then fail on their assertions, not here
        o.pinned.connect(lambda r: o.events.append(("pinned", r)))
    return o


def tb(overlay, name) -> QToolButton:
    found = overlay.toolbar.findChild(QToolButton, name)
    assert found is not None, name
    return found


def test_pin_button_is_shown(overlay):
    assert not tb(overlay, "pin").isHidden()


def test_pin_emits_pinned_with_the_marks(overlay):
    qi.drag(overlay, 100, 100, 300, 250)
    tb(overlay, "tool-rect").click()
    qi.drag(overlay, 120, 130, 220, 200)
    tb(overlay, "pin").click()
    assert overlay.events == [("pinned", Rect(100, 100, 200, 150))]
    assert len(overlay.marks) == 1
    assert overlay.state is OverlayState.FINISHED


def test_pin_keeps_text_being_typed(overlay):
    qi.drag(overlay, 100, 100, 300, 250)
    tb(overlay, "tool-text").click()
    qi.press(overlay, 150, 150)
    qi.release(overlay, 150, 150)
    overlay.editor.insert("pinned text")
    tb(overlay, "pin").click()
    assert [m.text for m in overlay.marks] == ["pinned text"]
    assert overlay.events == [("pinned", Rect(100, 100, 200, 150))]


def test_pin_while_drawing_does_nothing(overlay):
    qi.drag(overlay, 100, 100, 300, 250)
    tb(overlay, "tool-rect").click()
    qi.press(overlay, 120, 130)
    qi.move(overlay, 220, 200)
    tb(overlay, "pin").click()
    assert overlay.events == []


def test_session_action_is_pin(qtbot, overlay):
    session = OverlaySession([overlay])
    seen = []
    session.result.connect(lambda rect: seen.append((rect, session.action, session.marks)))
    qi.drag(overlay, 100, 100, 300, 250)
    tb(overlay, "tool-arrow").click()
    qi.drag(overlay, 120, 130, 220, 200)
    tb(overlay, "pin").click()
    assert seen == [(Rect(100, 100, 200, 150), "pin", overlay.marks)]
    assert session.finished
