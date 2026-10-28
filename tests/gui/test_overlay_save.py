"""M4 WI-23, WI-26: save from the capture toolbar, overlay side (PRD v1.1 F17-1, F17-5; plan D26, D28).

Pinned here:
- The save button, or Ctrl+S, while adjusting opens the overlay's save-as
  dialog (``save_dialog``: one ``QFileDialog`` child of the overlay, opened
  with ``open()``, reused; save mode, PNG only, default suffix ``png``),
  preset to ``save_target()``, asked again each time it opens. Text being
  typed is kept first (like Enter), also when Ctrl+S is pressed inside the
  text editor.
- Picking a file emits ``saved(rect)`` (never ``selected`` or ``pinned``),
  sets ``save_path`` and finishes the overlay; ``marks`` keeps the marks.
  Cancelling emits nothing: the selection and its marks stay, and saving
  again works.
- Nothing happens while selecting or while a mark is being drawn; an overlay
  without annotation (OCR, translate, code and table OCR) ignores Ctrl+S.
  An overlay abandoned while its dialog is open closes the dialog and ignores
  a file picked later.
- ``OverlaySession``: a saved overlay ends the session like a confirm, with
  ``action == "save"``, its marks and ``save_path``, set before ``result(rect)``.
"""

from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QColor, QImage, QKeyEvent
from PySide6.QtWidgets import QApplication, QFileDialog, QToolButton

from snapocr.geometry import Rect, ScreenInfo
from snapocr.gui.overlay import OverlaySession, OverlayState, SelectionOverlay
from support import qt_input as qi

pytestmark = pytest.mark.usefixtures("qapp")

BIG = ScreenInfo("A", Rect(0, 0, 800, 600), 1.0, Rect(0, 0, 800, 600))
AREA = Rect(100, 100, 200, 150)
PICKED = Path("D:/shots/picked.png")


def frozen() -> QImage:
    image = QImage(800, 600, QImage.Format.Format_RGB32)
    image.fill(QColor(200, 200, 200))
    return image


def recorded(qtbot, annotate=True, **kwargs) -> SelectionOverlay:
    o = SelectionOverlay(frozen(), BIG, annotate=annotate, **kwargs)
    qtbot.addWidget(o)
    o.events = []
    o.selected.connect(lambda r: o.events.append(("selected", r)))
    o.cancelled.connect(lambda: o.events.append(("cancelled", None)))
    o.pinned.connect(lambda r: o.events.append(("pinned", r)))
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


def dialog(overlay) -> QFileDialog:
    found = getattr(overlay, "save_dialog", None)
    assert isinstance(found, QFileDialog), "no save dialog"
    assert found.isVisible(), "the save dialog is not open"
    return found


def pick(overlay, path=PICKED) -> None:
    """The user picks ``path`` in the open save dialog."""
    dialog(overlay).fileSelected.emit(str(path))


def test_save_button_opens_a_png_save_dialog(overlay):
    qi.drag(overlay, 100, 100, 300, 250)
    tb(overlay, "save").click()
    d = dialog(overlay)
    assert d.parent() is overlay
    assert d.acceptMode() == QFileDialog.AcceptMode.AcceptSave
    assert d.defaultSuffix() == "png"
    assert d.nameFilters() == ["PNG 图片 (*.png)"]
    assert overlay.events == []
    assert overlay.state is OverlayState.ADJUSTING


def test_the_dialog_starts_at_the_save_target(qtbot, tmp_path):
    target = tmp_path / "snapocr_20261028_120000.png"
    o = recorded(qtbot, save_target=lambda: target)
    qi.drag(o, 100, 100, 300, 250)
    ctrl_s(o)
    d = dialog(o)
    assert Path(d.directory().absolutePath()) == tmp_path
    assert [Path(f) for f in d.selectedFiles()] == [target]


def test_the_save_target_is_asked_each_time(qtbot, tmp_path):
    targets = iter([tmp_path / "a.png", tmp_path / "b.png"])
    o = recorded(qtbot, save_target=lambda: next(targets))
    qi.drag(o, 100, 100, 300, 250)
    ctrl_s(o)
    first = dialog(o)
    first.reject()
    ctrl_s(o)
    assert dialog(o) is first
    assert [Path(f) for f in first.selectedFiles()] == [tmp_path / "b.png"]


def test_picking_a_file_emits_saved_with_the_marks(overlay):
    qi.drag(overlay, 100, 100, 300, 250)
    tb(overlay, "tool-rect").click()
    qi.drag(overlay, 120, 130, 220, 200)
    tb(overlay, "save").click()
    pick(overlay)
    assert overlay.events == [("saved", AREA)]
    assert overlay.save_path == PICKED
    assert len(overlay.marks) == 1
    assert overlay.state is OverlayState.FINISHED


def test_cancel_keeps_the_selection_and_marks(overlay):
    qi.drag(overlay, 100, 100, 300, 250)
    tb(overlay, "tool-rect").click()
    qi.drag(overlay, 120, 130, 220, 200)
    tb(overlay, "save").click()
    dialog(overlay).reject()
    assert overlay.events == []
    assert overlay.state is OverlayState.ADJUSTING
    assert overlay.selection == AREA
    assert len(overlay.marks) == 1
    assert not overlay.save_dialog.isVisible()
    tb(overlay, "save").click()
    pick(overlay)
    assert overlay.events == [("saved", AREA)]


def test_ctrl_s_saves_without_marks(overlay):
    qi.drag(overlay, 100, 100, 300, 250)
    ctrl_s(overlay)
    pick(overlay)
    assert overlay.events == [("saved", AREA)]
    assert overlay.marks == ()


def test_plain_s_does_not_save(overlay):
    qi.drag(overlay, 100, 100, 300, 250)
    qi.key(overlay, Qt.Key.Key_S)
    assert overlay.events == []
    assert getattr(overlay, "save_dialog", None) is None
    assert overlay.state is OverlayState.ADJUSTING


def test_ctrl_s_in_the_text_editor_keeps_the_text_then_saves(overlay):
    qi.drag(overlay, 100, 100, 300, 250)
    tb(overlay, "tool-text").click()
    qi.press(overlay, 150, 150)
    qi.release(overlay, 150, 150)
    overlay.editor.insert("saved text")
    ctrl_s(overlay.editor)
    assert overlay.editor is None
    assert [m.text for m in overlay.marks] == ["saved text"]
    pick(overlay)
    assert [m.text for m in overlay.marks] == ["saved text"]
    assert overlay.events == [("saved", AREA)]


def test_save_button_keeps_text_being_typed(overlay):
    qi.drag(overlay, 100, 100, 300, 250)
    tb(overlay, "tool-text").click()
    qi.press(overlay, 150, 150)
    qi.release(overlay, 150, 150)
    overlay.editor.insert("typed")
    tb(overlay, "save").click()
    pick(overlay)
    assert [m.text for m in overlay.marks] == ["typed"]
    assert overlay.events == [("saved", AREA)]


def test_ctrl_s_while_selecting_does_nothing(overlay):
    ctrl_s(overlay)
    qi.press(overlay, 100, 100)
    qi.move(overlay, 300, 250)
    ctrl_s(overlay)
    assert overlay.events == []
    assert getattr(overlay, "save_dialog", None) is None
    assert overlay.state is OverlayState.SELECTING


def test_save_while_drawing_does_nothing(overlay):
    qi.drag(overlay, 100, 100, 300, 250)
    tb(overlay, "tool-rect").click()
    qi.press(overlay, 120, 130)
    qi.move(overlay, 220, 200)
    tb(overlay, "save").click()
    ctrl_s(overlay)
    assert overlay.events == []
    assert getattr(overlay, "save_dialog", None) is None


def test_ctrl_s_after_finish_does_nothing(overlay):
    qi.drag(overlay, 100, 100, 300, 250)
    ctrl_s(overlay)
    pick(overlay)
    ctrl_s(overlay)
    assert overlay.events == [("saved", AREA)]
    assert not overlay.save_dialog.isVisible()


def test_abandon_closes_the_dialog_and_ignores_a_late_pick(overlay):
    qi.drag(overlay, 100, 100, 300, 250)
    ctrl_s(overlay)
    d = dialog(overlay)
    overlay.abandon()
    assert not d.isVisible()
    d.fileSelected.emit(str(PICKED))
    assert overlay.events == []


def test_overlay_without_annotation_ignores_ctrl_s(qtbot):
    plain = recorded(qtbot, annotate=False)
    qi.drag(plain, 100, 100, 300, 250)
    ctrl_s(plain)
    assert plain.events == []
    assert getattr(plain, "save_dialog", None) is None
    assert plain.state is OverlayState.ADJUSTING


def test_session_action_is_save(overlay):
    session = OverlaySession([overlay])
    seen = []
    session.result.connect(lambda rect: seen.append((rect, session.action, session.marks, session.save_path)))
    qi.drag(overlay, 100, 100, 300, 250)
    tb(overlay, "tool-arrow").click()
    qi.drag(overlay, 120, 130, 220, 200)
    tb(overlay, "save").click()
    pick(overlay)
    assert seen == [(AREA, "save", overlay.marks, PICKED)]
    assert session.finished
