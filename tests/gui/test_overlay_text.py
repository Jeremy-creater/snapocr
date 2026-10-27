"""M4 WI-5: the text tool (PRD F14-5; plan D9).

Pinned here:
- ``text_mark(text, top_left, style, dpr)``: blanks at both ends dropped;
  nothing left -> ``None``. Otherwise a ``Tool.TEXT`` mark of size
  ``scaled(FONT_LEVELS[level], dpr)`` whose points are ``top_left`` and
  ``top_left + (advance, height)`` of ``text_font(size)``.
- With the text tool picked, a left press inside the selection opens
  ``overlay.editor`` (a ``QLineEdit``, object name ``text-edit``) whose font
  is ``text_font(FONT_LEVELS[level])`` (logical px) and which covers the
  press point. Enter keeps the text as ``text_mark(text, press point, style,
  dpr)``; Esc drops it; neither confirms nor cancels the capture. A press
  anywhere while the editor is open keeps the text and opens nothing new; so
  do changing the tool and the done button (which then confirms).
- The style at the moment the text is kept is used; the editor shows it.
"""

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFontMetrics, QImage
from PySide6.QtWidgets import QLineEdit, QToolButton

from snapocr.annotate import DEFAULT_STYLE, FONT_LEVELS, PALETTE, Style, Tool, scaled
from snapocr.geometry import Rect, ScreenInfo, local_to_physical
from snapocr.gui.marks_paint import text_font, text_mark
from snapocr.gui.overlay import OverlayState, SelectionOverlay
from support import qt_input as qi

pytestmark = pytest.mark.usefixtures("qapp")

BIG = ScreenInfo("A", Rect(0, 0, 800, 600), 1.0, Rect(0, 0, 800, 600))
HI = ScreenInfo("B", Rect(800, 0, 400, 300), 2.0, Rect(1600, 0, 800, 600))


def frozen(screen: ScreenInfo) -> QImage:
    image = QImage(screen.physical.w, screen.physical.h, QImage.Format.Format_RGB32)
    image.fill(QColor(200, 200, 200))
    return image


class Probe:
    def __init__(self, overlay):
        self.selected, self.cancelled = [], 0
        overlay.selected.connect(self.selected.append)
        overlay.cancelled.connect(self._cancel)

    def _cancel(self):
        self.cancelled += 1


@pytest.fixture
def text_overlay(qtbot):
    def factory(screen=BIG):
        overlay = SelectionOverlay(frozen(screen), screen, annotate=True)
        qtbot.addWidget(overlay)
        probe = Probe(overlay)
        if screen is BIG:
            qi.drag(overlay, 100, 100, 500, 400)
        else:
            qi.drag(overlay, 50, 50, 300, 250)
        tb(overlay, "tool-text").click()
        return overlay, probe

    return factory


def tb(overlay, name) -> QToolButton:
    assert overlay.toolbar is not None
    found = overlay.toolbar.findChild(QToolButton, name)
    assert found is not None, name
    return found


def open_editor(overlay, x, y) -> QLineEdit:
    qi.press(overlay, x, y)
    qi.release(overlay, x, y)
    editor = overlay.editor
    assert isinstance(editor, QLineEdit), "no editor"
    assert editor.objectName() == "text-edit"
    return editor


def editor_gone(overlay) -> bool:
    return overlay.editor is None and all(e.isHidden() for e in overlay.findChildren(QLineEdit, "text-edit"))


# --- text_mark --------------------------------------------------------------------


@pytest.mark.parametrize("text", ["", "   ", "\t"])
def test_blank_text_makes_no_mark(text):
    assert text_mark(text, (10, 10), DEFAULT_STYLE, 1.0) is None


@pytest.mark.parametrize(("level", "dpr"), [(0, 1.0), (1, 1.5), (2, 2.0)])
def test_text_mark_size_and_extent(qapp, level, dpr):
    mark = text_mark("  标注 Ab ", (-300, 40), Style(PALETTE[2], level), dpr)
    size = scaled(FONT_LEVELS[level], dpr)
    metrics = QFontMetrics(text_font(size))
    far = (-300 + metrics.horizontalAdvance("标注 Ab"), 40 + metrics.height())
    assert mark.tool is Tool.TEXT and mark.text == "标注 Ab"
    assert mark.size == size and mark.color == PALETTE[2]
    assert mark.points == ((-300, 40), far)


def test_text_font_pixel_size():
    assert text_font(28).pixelSize() == 28


# --- editor ---------------------------------------------------------------------------


def test_press_opens_an_editor_at_the_point(text_overlay):
    overlay, probe = text_overlay()
    editor = open_editor(overlay, 200, 150)
    assert editor.isVisibleTo(overlay)
    assert editor.font().pixelSize() == FONT_LEVELS[DEFAULT_STYLE.level]
    assert editor.geometry().contains(200, 150) or editor.geometry().contains(201, 151)
    assert overlay.marks == () and probe.selected == [] and probe.cancelled == 0


def test_enter_keeps_the_text(text_overlay):
    overlay, probe = text_overlay()
    editor = open_editor(overlay, 200, 150)
    editor.insert("标注 Ab")
    qi.key(editor, Qt.Key.Key_Return)
    assert overlay.marks == (text_mark("标注 Ab", (200, 150), DEFAULT_STYLE, 1.0),)
    assert editor_gone(overlay)
    assert probe.selected == [] and probe.cancelled == 0
    assert overlay.state is OverlayState.ADJUSTING
    assert tb(overlay, "undo").isEnabled()


def test_escape_drops_only_the_text(text_overlay):
    overlay, probe = text_overlay()
    editor = open_editor(overlay, 200, 150)
    editor.insert("abc")
    qi.key(editor, Qt.Key.Key_Escape)
    assert overlay.marks == () and editor_gone(overlay)
    assert probe.cancelled == 0 and overlay.state is OverlayState.ADJUSTING
    qi.key(overlay, Qt.Key.Key_Escape)
    assert probe.cancelled == 1


def test_overlay_keys_follow_the_same_rules_while_editing(text_overlay):
    overlay, probe = text_overlay()
    open_editor(overlay, 200, 150).insert("one")
    qi.key(overlay, Qt.Key.Key_Return)  # the overlay got the key: keep the text, do not confirm
    assert [m.text for m in overlay.marks] == ["one"] and probe.selected == []
    open_editor(overlay, 300, 250).insert("two")
    qi.key(overlay, Qt.Key.Key_Escape)  # drop the text, do not cancel
    assert [m.text for m in overlay.marks] == ["one"] and probe.cancelled == 0


def test_empty_text_leaves_nothing(text_overlay):
    overlay, _ = text_overlay()
    editor = open_editor(overlay, 200, 150)
    editor.insert("   ")
    qi.key(editor, Qt.Key.Key_Enter)
    assert overlay.marks == () and editor_gone(overlay)
    assert not tb(overlay, "undo").isEnabled()


def test_press_elsewhere_keeps_the_text_and_opens_nothing(text_overlay):
    overlay, _ = text_overlay()
    open_editor(overlay, 200, 150).insert("first")
    qi.press(overlay, 300, 300)
    qi.release(overlay, 300, 300)
    assert [m.text for m in overlay.marks] == ["first"]
    assert overlay.editor is None
    open_editor(overlay, 300, 300).insert("second")
    qi.press(overlay, 700, 550)  # outside the selection
    qi.release(overlay, 700, 550)
    assert [m.text for m in overlay.marks] == ["first", "second"]


def test_press_outside_the_selection_opens_nothing(text_overlay):
    overlay, _ = text_overlay()
    qi.press(overlay, 700, 550)
    qi.release(overlay, 700, 550)
    assert overlay.editor is None and overlay.findChild(QLineEdit, "text-edit") is None


def test_changing_the_tool_keeps_the_text(text_overlay):
    overlay, _ = text_overlay()
    open_editor(overlay, 200, 150).insert("kept")
    tb(overlay, "tool-rect").click()
    assert [m.text for m in overlay.marks] == ["kept"] and overlay.editor is None


def test_done_keeps_the_text_and_confirms(text_overlay):
    overlay, probe = text_overlay()
    open_editor(overlay, 200, 150).insert("done")
    tb(overlay, "done").click()
    assert probe.selected == [Rect(100, 100, 400, 300)]
    assert [m.text for m in overlay.marks] == ["done"]


def test_style_changed_while_typing_is_used(text_overlay):
    overlay, _ = text_overlay()
    editor = open_editor(overlay, 200, 150)
    editor.insert("blue")
    tb(overlay, "color-4").click()
    tb(overlay, "level-2").click()
    assert editor.font().pixelSize() == FONT_LEVELS[2]
    assert PALETTE[4] in editor.styleSheet()
    qi.key(editor, Qt.Key.Key_Return)
    assert overlay.marks == (text_mark("blue", (200, 150), Style(PALETTE[4], 2), 1.0),)


def test_typing_goes_into_the_editor(text_overlay, qtbot):
    overlay, _ = text_overlay()
    editor = open_editor(overlay, 200, 150)
    qtbot.keyClicks(editor, "typed")
    assert editor.text() == "typed"
    qi.key(editor, Qt.Key.Key_Return)
    assert [m.text for m in overlay.marks] == ["typed"]


def test_editor_grows_with_the_text(text_overlay):
    overlay, _ = text_overlay()
    editor = open_editor(overlay, 200, 150)
    empty_width = editor.width()
    editor.insert("a much longer line of text")
    assert editor.width() > empty_width


def test_text_on_a_scaled_screen(text_overlay):
    overlay, _ = text_overlay(HI)
    editor = open_editor(overlay, 120, 80)
    editor.insert("缩放")
    qi.key(editor, Qt.Key.Key_Return)
    at = local_to_physical(HI, 120, 80)
    assert overlay.marks == (text_mark("缩放", at, DEFAULT_STYLE, 2.0),)
    assert overlay.marks[0].size == 40


def test_undo_removes_text(text_overlay):
    overlay, _ = text_overlay()
    open_editor(overlay, 200, 150).insert("x")
    qi.key(overlay.editor, Qt.Key.Key_Return)
    tb(overlay, "undo").click()
    assert overlay.marks == ()


def test_kept_text_is_painted(text_overlay):
    overlay, _ = text_overlay()
    open_editor(overlay, 120, 120).insert("████")
    qi.key(overlay.editor, Qt.Key.Key_Return)
    (x0, y0), (x1, y1) = overlay.marks[0].points
    image = overlay.grab().toImage()
    red = QColor(PALETTE[0])
    inked = [
        (x, y)
        for y in range(y0, y1)
        for x in range(x0, x1)
        if abs(image.pixelColor(x, y).red() - red.red()) < 40 and image.pixelColor(x, y).green() < 120
    ]
    assert len(inked) > 20
    assert QPointF(x0, y0) == QPointF(120, 120)
