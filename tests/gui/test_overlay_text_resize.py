"""M4 WI-19: resizing text by dragging its handle; picking text with the text tool (PRD F14-11; plan D18).

Pinned here:
- A kept text becomes the picked mark. A picked text has a filled handle at
  ``text_handle(mark, tol)`` (the outline's bottom-right corner), and the
  cursor shows a diagonal resize arrow over it.
- A press within ``tol`` of the handle and a drag resize the text to
  ``fit_text(mark, text_resize_size(mark, dx, dy, dpr))`` (physical drag),
  shown while dragging, kept on release as one undo step; no movement, no
  step. This works with the text tool and with no tool.
- With the text tool and no editor open, a press on a text mark picks it and
  a drag moves it (no editor opens); a press elsewhere in the selection
  unpicks and opens the editor. ``Delete`` removes a picked text.
"""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QToolButton

from snapocr.annotate import moved, text_handle, text_resize_size
from snapocr.geometry import Rect, ScreenInfo, physical_to_local
from snapocr.gui.marks_paint import fit_text
from snapocr.gui.overlay import HANDLE_SIZE, SelectionOverlay
from support import qt_input as qi

pytestmark = pytest.mark.usefixtures("qapp")

BIG = ScreenInfo("A", Rect(0, 0, 800, 600), 1.0, Rect(0, 0, 800, 600))
HI = ScreenInfo("B", Rect(800, 0, 400, 300), 2.0, Rect(1600, 0, 800, 600))
BORDER = QColor(30, 144, 255)


def tb(overlay, name) -> QToolButton:
    found = overlay.toolbar.findChild(QToolButton, name)
    assert found is not None, name
    return found


def tol(screen: ScreenInfo) -> int:
    return max(1, round(HANDLE_SIZE / 2 * screen.dpr))


def make(qtbot, screen=BIG):
    image = QImage(screen.physical.w, screen.physical.h, QImage.Format.Format_RGB32)
    image.fill(QColor(200, 200, 200))
    overlay = SelectionOverlay(image, screen, annotate=True)
    qtbot.addWidget(overlay)
    qi.drag(overlay, 20, 20, 380, 280)
    tb(overlay, "tool-text").click()
    return overlay


def click(overlay, x, y):
    qi.press(overlay, x, y)
    qi.release(overlay, x, y)


def write(overlay, x, y, text="标注 Ab"):
    click(overlay, x, y)
    assert overlay.editor is not None, "no editor"
    overlay.editor.insert(text)
    qi.key(overlay.editor, Qt.Key.Key_Return)
    assert overlay.editor is None
    return overlay.marks[-1]


def handle_at(overlay, screen, mark) -> tuple[float, float]:
    return physical_to_local(screen, *text_handle(mark, tol(screen)))


def test_kept_text_is_picked(qtbot):
    overlay = make(qtbot)
    write(overlay, 50, 50)
    assert overlay.picked == 0
    write(overlay, 50, 150)
    assert overlay.picked == 1


def test_dragging_the_handle_resizes(qtbot):
    overlay = make(qtbot)
    text = write(overlay, 50, 50)
    hx, hy = handle_at(overlay, BIG, text)
    qi.press(overlay, hx, hy)
    qi.move(overlay, hx + 40, hy + 10)
    assert overlay.marks == (text,)  # not kept yet
    qi.release(overlay, hx + 40, hy + 10)
    resized = fit_text(text, text_resize_size(text, 40, 10, 1.0))
    assert resized.size > text.size
    assert overlay.marks == (resized,) and overlay.picked == 0
    assert overlay.editor is None
    tb(overlay, "undo").click()
    assert overlay.marks == (text,)


def test_resize_is_shown_while_dragging(qtbot):
    overlay = make(qtbot)
    text = write(overlay, 50, 50)
    hx, hy = handle_at(overlay, BIG, text)
    before = overlay.grab().toImage()
    qi.press(overlay, hx, hy)
    qi.move(overlay, hx + 60, hy + 24)
    after = overlay.grab().toImage()
    right = round(hx) + 10
    assert any(before.pixel(x, y) != after.pixel(x, y) for y in range(40, 200) for x in range(right, 370))


def test_handle_click_without_moving_adds_no_step(qtbot):
    overlay = make(qtbot)
    text = write(overlay, 50, 50)
    click(overlay, *handle_at(overlay, BIG, text))
    assert overlay.marks == (text,) and overlay.editor is None
    tb(overlay, "undo").click()
    assert overlay.marks == ()


def test_resize_with_no_tool(qtbot):
    overlay = make(qtbot)
    text = write(overlay, 50, 50)
    tb(overlay, "tool-text").click()  # no tool: the pick is cleared
    assert overlay.picked is None
    click(overlay, 55, 55)
    assert overlay.picked == 0
    hx, hy = handle_at(overlay, BIG, text)
    qi.press(overlay, hx, hy)
    qi.move(overlay, hx - 10, hy - 4)
    qi.release(overlay, hx - 10, hy - 4)
    assert overlay.marks == (fit_text(text, text_resize_size(text, -10, -4, 1.0)),)


def test_resize_on_a_scaled_screen_is_physical(qtbot):
    overlay = make(qtbot, HI)
    text = write(overlay, 50, 50)
    hx, hy = handle_at(overlay, HI, text)
    qi.press(overlay, hx, hy)
    qi.move(overlay, hx + 20, hy + 5)
    qi.release(overlay, hx + 20, hy + 5)
    assert overlay.marks == (fit_text(text, text_resize_size(text, 40, 10, 2.0)),)


def test_text_tool_press_on_text_picks_and_moves_it(qtbot):
    overlay = make(qtbot)
    text = write(overlay, 50, 50)
    click(overlay, 200, 200)  # elsewhere: unpick, open the editor
    assert overlay.picked is None and overlay.editor is not None
    qi.key(overlay.editor, Qt.Key.Key_Escape)
    qi.press(overlay, 55, 55)
    assert overlay.picked == 0 and overlay.editor is None
    qi.move(overlay, 75, 65)
    qi.release(overlay, 75, 65)
    assert overlay.marks == (moved(text, 20, 10),)
    assert overlay.editor is None


def test_delete_removes_picked_text(qtbot):
    overlay = make(qtbot)
    write(overlay, 50, 50)
    qi.key(overlay, Qt.Key.Key_Delete)
    assert overlay.marks == () and overlay.picked is None


def test_handle_is_drawn(qtbot):
    overlay = make(qtbot)
    text = write(overlay, 50, 50)
    hx, hy = handle_at(overlay, BIG, text)
    shot = overlay.grab().toImage()
    assert shot.pixelColor(round(hx) - 2, round(hy) - 2) == BORDER  # inside the square, off the outline


def test_no_handle_for_other_marks(qtbot):
    overlay = make(qtbot)
    tb(overlay, "tool-rect").click()
    qi.drag(overlay, 100, 100, 200, 180)
    tb(overlay, "tool-rect").click()
    click(overlay, 110, 110)
    assert overlay.picked == 0
    shot = overlay.grab().toImage()
    # the rectangle's outline corner (bounds 98..202, grown by tol 4) has no filled handle
    assert shot.pixelColor(204, 184) != BORDER


def test_cursor_over_the_handle(qtbot):
    overlay = make(qtbot)
    text = write(overlay, 50, 50)
    hx, hy = handle_at(overlay, BIG, text)
    qi.move(overlay, hx, hy, qi.NONE)
    assert overlay.cursor().shape() == Qt.CursorShape.SizeFDiagCursor
    qi.move(overlay, 300, 250, qi.NONE)
    assert overlay.cursor().shape() == Qt.CursorShape.CrossCursor
    tb(overlay, "tool-text").click()
    click(overlay, 55, 55)
    qi.move(overlay, hx, hy, qi.NONE)
    assert overlay.cursor().shape() == Qt.CursorShape.SizeFDiagCursor
    qi.move(overlay, 300, 250, qi.NONE)
    assert overlay.cursor().shape() == Qt.CursorShape.ArrowCursor
