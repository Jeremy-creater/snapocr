"""Frozen-screen selection overlay, one window per screen (F6-1, F6-3, F6-4, F6-5, F14; plan D4).

Each overlay shows its screen's part of the capture, dimmed, and lets the user
drag a selection, then adjust it (handles, move, re-select) and confirm with
Enter or a double click inside. All coordinates are physical pixels; the
geometry rules live in ``snapocr.geometry`` (WI-3). A selection never leaves
the screen it started on.

With ``annotate=True`` (the capture action, PRD F14) an adjusted selection
gets the annotation toolbar. While no tool is picked and nothing is drawn the
selection still adjusts as before; after that it is fixed (F14-3) and drags
inside it draw marks (``snapocr.annotate``, drawn by ``marks_paint``).
The text tool opens a line editor at the click instead (F14-5); Enter or a
click elsewhere keeps the text, Esc drops only the text. The toolbar's save
button or Ctrl+S opens a save-as dialog, keeping text being typed; a picked
file ends it with ``saved`` and ``save_path`` (F17-1, M4 plan D28).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import replace
from enum import Enum
from pathlib import Path

from PySide6.QtCore import QObject, QPoint, QPointF, QRect, QRectF, Qt, Signal, SignalInstance
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QKeyEvent, QMouseEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QFileDialog, QLineEdit, QWidget

from snapocr.annotate import (
    DEFAULT_STYLE,
    FONT_LEVELS,
    Board,
    Mark,
    Style,
    Tool,
    drag_mark,
    hit_mark,
    mark_bounds,
    moved,
    number_mark,
    pen_mark,
    text_handle,
    text_resize_size,
    toolbar_place,
    with_level,
)
from snapocr.geometry import (
    Handle,
    Point,
    Rect,
    ScreenInfo,
    hit_handle,
    is_cancel_size,
    label_place,
    local_to_physical,
    move,
    physical_to_local,
    resize,
    selection_rect,
    size_text,
)
from snapocr.gui.annotate_toolbar import AnnotateToolbar
from snapocr.gui.marks_paint import fit_text, paint_marks, text_font, text_mark

HANDLE_SIZE = 7  # logical px, drawn centred on corners and edge midpoints
HANDLE_MARGIN = 5  # border and handles stay within this many logical px of the edges
TOOLBAR_GAP = 6  # logical px between the selection and the toolbar (M4 plan D12)
EDITOR_INSET = (3, 2)  # logical px from the editor's corner to where its text starts
EDITOR_MIN_WIDTH = 40  # logical px
_DIM = QColor(0, 0, 0, 110)
_BORDER = QColor(30, 144, 255)
LABEL_GAP = 4  # logical px between the selection and its size label (F18-6)
LABEL_PAD = (6, 2)  # logical px around the label's text
_LABEL_BACK = QColor(0, 0, 0, 170)
_LABEL_FONT_PX = 12

_CURSORS = {
    Handle.NONE: Qt.CursorShape.CrossCursor,
    Handle.INSIDE: Qt.CursorShape.SizeAllCursor,
    Handle.NW: Qt.CursorShape.SizeFDiagCursor,
    Handle.SE: Qt.CursorShape.SizeFDiagCursor,
    Handle.NE: Qt.CursorShape.SizeBDiagCursor,
    Handle.SW: Qt.CursorShape.SizeBDiagCursor,
    Handle.N: Qt.CursorShape.SizeVerCursor,
    Handle.S: Qt.CursorShape.SizeVerCursor,
    Handle.W: Qt.CursorShape.SizeHorCursor,
    Handle.E: Qt.CursorShape.SizeHorCursor,
}


class OverlayState(Enum):
    SELECTING = "selecting"
    ADJUSTING = "adjusting"
    FINISHED = "finished"


def _inside(rect: Rect, p: Point) -> bool:
    return rect.x <= p[0] <= rect.x + rect.w and rect.y <= p[1] <= rect.y + rect.h


class TextEditor(QLineEdit):
    """The line editor of the text tool: Enter keeps, Esc drops; neither reaches the overlay."""

    committed = Signal()
    discarded = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.committed.emit()
        elif event.key() == Qt.Key.Key_Escape:
            self.discarded.emit()
        else:
            super().keyPressEvent(event)


class SelectionOverlay(QWidget):
    selected = Signal(object)  # Rect, physical pixels
    cancelled = Signal()
    style_changed = Signal(object)  # Style, annotate mode only (M4 plan D13)
    pinned = Signal(object)  # Rect: the toolbar's pin button (F15-1)
    saved = Signal(object)  # Rect: a file picked in the save dialog, in save_path (F17-1)

    def __init__(
        self,
        frozen: QImage,
        screen: ScreenInfo,
        parent: QWidget | None = None,
        *,
        annotate: bool = False,
        style: Style = DEFAULT_STYLE,
        save_target: Callable[[], Path] | None = None,
    ) -> None:
        super().__init__(parent)
        self._save_target = save_target
        self.save_dialog: QFileDialog | None = None  # created on the first save (M4 plan D28)
        self.save_path: Path | None = None  # the file picked in it
        p = screen.physical
        if (frozen.width(), frozen.height()) != (p.w, p.h):
            raise ValueError(f"frozen image is {frozen.width()}x{frozen.height()}, screen {screen.name} is {p.w}x{p.h}")
        self._frozen = frozen
        self._screen = screen
        self._state = OverlayState.SELECTING
        self._rect: Rect | None = None
        # The drag in progress: (handle, press point, rect at press). Handle.NONE = new selection.
        self._drag: tuple[Handle, Point, Rect | None] | None = None
        self._tol = max(1, round(HANDLE_SIZE / 2 * screen.dpr))
        self._board = Board()
        self._drawing: Point | None = None  # press point of the mark being drawn
        self._stroke: list[Point] = []  # the pen tool's points so far
        self._picked: int | None = None  # index of the picked mark (F14-8)
        self._moving: Point | None = None  # press point while dragging the picked mark
        self._moved: Mark | None = None  # the picked mark where the drag has put it
        self._resizing: Point | None = None  # press point while dragging a text's handle (F14-11)
        self._draft: Mark | None = None
        self._editor: TextEditor | None = None
        self._editor_at: Point = (0, 0)  # physical top-left of the text being typed
        self.toolbar: AnnotateToolbar | None = None
        if annotate:
            self.toolbar = AnnotateToolbar(style, self, show_pin=True)
            self.toolbar.hide()
            self.toolbar.tool_changed.connect(self._tool_changed)
            self.toolbar.style_changed.connect(self.style_changed)
            self.toolbar.style_changed.connect(self._style_editor)
            self.toolbar.color_clicked.connect(lambda c: self._restyle(lambda m: replace(m, color=c)))
            self.toolbar.level_clicked.connect(lambda lv: self._restyle(lambda m: self._with_level(m, lv)))
            self.toolbar.undo_requested.connect(self._undo)
            self.toolbar.cancel_requested.connect(lambda: self._finish(None))
            self.toolbar.done_requested.connect(self._done)
            self.toolbar.pin_requested.connect(lambda: self._leave(self.pinned))
            self.toolbar.save_requested.connect(self._ask_save)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        logical = screen.logical
        self.setGeometry(QRect(logical.x, logical.y, logical.w, logical.h))

    @property
    def state(self) -> OverlayState:
        return self._state

    @property
    def selection(self) -> Rect | None:
        return self._rect

    @property
    def marks(self) -> tuple[Mark, ...]:
        """The finished marks, in drawing order (physical pixels)."""
        return self._board.marks

    @property
    def picked(self) -> int | None:
        """Index in ``marks`` of the mark picked with no tool (F14-8), or ``None``."""
        return self._picked

    @property
    def size_label(self) -> tuple[str, QRect] | None:
        """F18-6: the selection's physical size and where it is drawn (logical), while there is one."""
        if self._rect is None or self._state is OverlayState.FINISHED:
            return None
        text = size_text(self._rect)
        metrics = QFontMetrics(self._label_font())
        size = (metrics.horizontalAdvance(text) + 2 * LABEL_PAD[0], metrics.height() + 2 * LABEL_PAD[1])
        sel = self._local_rect(self._rect)
        local = Rect(math.floor(sel.left()), math.floor(sel.top()), 0, 0)
        x, y = label_place(local, size, Rect(0, 0, self.width(), self.height()), LABEL_GAP)
        return text, QRect(x, y, *size)

    @staticmethod
    def _label_font() -> QFont:
        font = QFont()
        font.setPixelSize(_LABEL_FONT_PX)
        return font

    @property
    def editor(self) -> TextEditor | None:
        """The open text editor (F14-5), if any."""
        return self._editor

    def abandon(self) -> None:
        """Stop reacting to input without emitting anything (the session ended elsewhere)."""
        self._state = OverlayState.FINISHED
        self._drag = None
        self._drawing = None
        if self.save_dialog is not None:
            self.save_dialog.reject()

    # --- annotation ----------------------------------------------------------

    @property
    def _tool(self) -> Tool | None:
        return None if self.toolbar is None else self.toolbar.tool

    @property
    def _locked(self) -> bool:
        """F14-3: once a tool is picked or a mark drawn, the selection stays put."""
        return self._tool is not None or bool(self._board.marks)

    @property
    def _dragging_mark(self) -> bool:
        return self._moving is not None or self._resizing is not None

    def _on_handle(self, p: Point) -> bool:
        """Whether ``p`` is on the picked text's resize handle (F14-11)."""
        if self._picked is None or self._board.marks[self._picked].tool is not Tool.TEXT:
            return False
        hx, hy = text_handle(self._board.marks[self._picked], self._tol)
        return max(abs(p[0] - hx), abs(p[1] - hy)) <= self._tol

    def _text_at(self, p: Point) -> int | None:
        i = hit_mark(self._board.marks, p, self._tol)
        return i if i is not None and self._board.marks[i].tool is Tool.TEXT else None

    def _tool_changed(self, tool: Tool | None) -> None:
        self._close_editor(keep=True)
        self._picked = None
        self.setCursor(Qt.CursorShape.CrossCursor if tool is not None else Qt.CursorShape.ArrowCursor)
        self.update()

    def _undo(self) -> None:
        if self._board.undo():
            self._picked = None
            self._marks_changed()

    def _marks_changed(self) -> None:
        assert self.toolbar is not None
        self.toolbar.set_undo_enabled(self._board.can_undo)
        self.update()

    def _with_level(self, mark: Mark, level: int) -> Mark:
        mark = with_level(mark, level, self._screen.dpr)
        return fit_text(mark, mark.size) if mark.tool is Tool.TEXT else mark

    def _restyle(self, change: Callable[[Mark], Mark]) -> None:
        """F14-10: a colour or level click changes the picked mark, as one undo step."""
        if self._picked is None or self._dragging_mark:
            return
        marks = list(self._board.marks)
        new = change(marks[self._picked])
        if new != marks[self._picked]:
            marks[self._picked] = new
            self._board.change(tuple(marks))
            self._marks_changed()

    def _open_editor(self, p: Point) -> None:
        self._editor_at = p
        x, y = physical_to_local(self._screen, *p)
        editor = TextEditor(self)
        editor.setObjectName("text-edit")
        editor.setFont(text_font(FONT_LEVELS[self.toolbar.style.level]))
        editor.textChanged.connect(self._fit_editor)
        editor.committed.connect(lambda: self._close_editor(keep=True))
        editor.discarded.connect(lambda: self._close_editor(keep=False))
        editor.move(QPoint(round(x) - EDITOR_INSET[0], round(y) - EDITOR_INSET[1]))
        self._editor = editor
        self._style_editor(self.toolbar.style)
        self._fit_editor()
        editor.show()
        editor.setFocus()

    def _style_editor(self, style: Style) -> None:
        if self._editor is not None:
            self._editor.setFont(text_font(FONT_LEVELS[style.level]))
            self._editor.setStyleSheet(
                f"QLineEdit {{ color: {style.color}; background: transparent;"
                f" border: 1px dashed {style.color}; padding: 0px; }}"
            )
            self._fit_editor()

    def _fit_editor(self) -> None:
        editor = self._editor
        width = editor.fontMetrics().horizontalAdvance(editor.text()) + 4 * EDITOR_INSET[0]
        editor.resize(max(EDITOR_MIN_WIDTH, width), editor.sizeHint().height())

    def _close_editor(self, *, keep: bool) -> None:
        editor, self._editor = self._editor, None
        if editor is None:
            return
        if keep:
            mark = text_mark(editor.text(), self._editor_at, self.toolbar.style, self._screen.dpr)
            if mark is not None:
                self._board.add(mark)
                self._picked = len(self._board.marks) - 1  # F14-11: ready to move or resize
        editor.hide()
        editor.deleteLater()
        self.setFocus()
        self._marks_changed()

    def _drawn(self, p: Point) -> Mark | None:
        """The mark of the drawing drag so far, ending at ``p``."""
        style, dpr = self.toolbar.style, self._screen.dpr
        if self._tool is Tool.PEN:
            self._stroke.append(p)
            return pen_mark(self._stroke, style, dpr)
        return drag_mark(self._tool, self._drawing, p, style, dpr)

    def _place_toolbar(self) -> None:
        if self.toolbar is None:
            return
        if self._state is not OverlayState.ADJUSTING:
            self.toolbar.hide()
            return
        sel = self._local_rect(self._rect)
        x0, y0 = math.floor(sel.left()), math.floor(sel.top())
        local = Rect(x0, y0, math.ceil(sel.right()) - x0, math.ceil(sel.bottom()) - y0)
        hint = self.toolbar.sizeHint()
        x, y = toolbar_place(local, (hint.width(), hint.height()), Rect(0, 0, self.width(), self.height()), TOOLBAR_GAP)
        self.toolbar.setGeometry(x, y, hint.width(), hint.height())
        self.toolbar.show()
        self.toolbar.raise_()

    # --- results -----------------------------------------------------------

    def _finish(self, rect: Rect | None) -> None:
        self.abandon()
        if rect is None or is_cancel_size(rect):
            self.cancelled.emit()
        else:
            self.selected.emit(rect)

    def _done(self) -> None:
        self._close_editor(keep=True)
        self._confirm()

    def _leave(self, signal: SignalInstance) -> None:
        """Pin or save: like a confirm, but reported on ``signal`` (F15-1, F17-1)."""
        self._close_editor(keep=True)
        if self._state is OverlayState.ADJUSTING and self._drag is None and self._drawing is None:
            self.abandon()
            signal.emit(self._rect)

    def _ask_save(self) -> None:
        """F17-1: the save-as dialog, over the overlay; a picked file ends the overlay with ``saved``."""
        self._close_editor(keep=True)
        if self._state is not OverlayState.ADJUSTING or self._drag is not None or self._drawing is not None:
            return
        if self.save_dialog is None:
            self.save_dialog = QFileDialog(self, "保存截图")
            self.save_dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
            self.save_dialog.setNameFilter("PNG 图片 (*.png)")
            self.save_dialog.setDefaultSuffix("png")
            self.save_dialog.fileSelected.connect(self._save_to)
        if self._save_target is not None:
            target = self._save_target()
            self.save_dialog.setDirectory(str(target.parent))
            self.save_dialog.selectFile(str(target))
        self.save_dialog.open()

    def _save_to(self, path: str) -> None:
        if self._state is OverlayState.ADJUSTING:  # not abandoned meanwhile
            self.save_path = Path(path)
            self._leave(self.saved)

    def _confirm(self) -> None:
        if self._state is OverlayState.ADJUSTING and self._drag is None and self._drawing is None:
            self._finish(self._rect)

    # --- input -------------------------------------------------------------

    def _point(self, event: QMouseEvent) -> Point:
        pos = event.position()
        return local_to_physical(self._screen, pos.x(), pos.y())

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._state is OverlayState.FINISHED:
            return
        if event.button() == Qt.MouseButton.RightButton:
            self._finish(None)
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        p = self._point(event)
        if self._state is OverlayState.ADJUSTING and self._locked:
            if self._editor is not None:  # a click elsewhere keeps the text (F14-5)
                self._close_editor(keep=True)
            elif self._on_handle(p):
                self._resizing = p
            elif self._tool is Tool.TEXT and (i := self._text_at(p)) is not None:
                self._picked, self._moving = i, p
                self.update()
            elif self._tool is Tool.TEXT and _inside(self._rect, p):
                self._picked = None
                self._open_editor(p)
            elif self._tool is Tool.NUMBER and _inside(self._rect, p):
                self._board.add(number_mark(p, self._board.marks, self.toolbar.style, self._screen.dpr))
                self._marks_changed()
            elif self._tool is not None and _inside(self._rect, p):
                self._drawing = p
                self._stroke = [p]
            elif self._tool is None:
                self._picked = hit_mark(self._board.marks, p, self._tol)
                self._moving = None if self._picked is None else p
                self.update()
            return
        handle = Handle.NONE
        if self._state is OverlayState.ADJUSTING:
            handle = hit_handle(self._rect, p, self._tol)
        if handle is Handle.NONE:
            self._state = OverlayState.SELECTING
            self._rect = selection_rect(self._screen, p, p)
            self.setCursor(Qt.CursorShape.CrossCursor)
            self._place_toolbar()
        self._drag = (handle, p, self._rect)
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._state is OverlayState.FINISHED:
            return
        p = self._point(event)
        if self._drawing is not None:
            self._draft = self._drawn(p)
            self.update()
            return
        if self._moving is not None:
            self._moved = moved(self._board.marks[self._picked], p[0] - self._moving[0], p[1] - self._moving[1])
            self.update()
            return
        if self._resizing is not None:
            mark = self._board.marks[self._picked]
            dx, dy = p[0] - self._resizing[0], p[1] - self._resizing[1]
            self._moved = fit_text(mark, text_resize_size(mark, dx, dy, self._screen.dpr))
            self.update()
            return
        if self._drag is None:
            if self._state is OverlayState.ADJUSTING and not self._locked:
                self.setCursor(_CURSORS[hit_handle(self._rect, p, self._tol)])
            elif self._state is OverlayState.ADJUSTING:
                self.setCursor(self._locked_cursor(p))
            return
        handle, start, start_rect = self._drag
        if handle is Handle.NONE:
            self._rect = selection_rect(self._screen, start, p)
        elif handle is Handle.INSIDE:
            self._rect = move(start_rect, p[0] - start[0], p[1] - start[1], self._screen)
        else:
            self._rect = resize(start_rect, handle, p, self._screen)
        self._place_toolbar()
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._state is OverlayState.FINISHED or event.button() != Qt.MouseButton.LeftButton:
            return
        if self._drawing is not None:
            mark = self._drawn(self._point(event))
            self._drawing, self._draft = None, None
            if mark is not None:
                self._board.add(mark)
            self._marks_changed()
            return
        if self._dragging_mark:
            self.mouseMoveEvent(event)
            marks = list(self._board.marks)
            if self._moved != marks[self._picked]:
                marks[self._picked] = self._moved
                self._board.change(tuple(marks))
            self._moving, self._resizing, self._moved = None, None, None
            self._marks_changed()
            return
        if self._drag is None:
            return
        self.mouseMoveEvent(event)
        handle = self._drag[0]
        self._drag = None
        if handle is Handle.NONE:
            if is_cancel_size(self._rect):
                self._finish(None)
                return
            self._state = OverlayState.ADJUSTING
            self._place_toolbar()
        self.update()

    def _locked_cursor(self, p: Point) -> Qt.CursorShape:
        if self._on_handle(p):
            return Qt.CursorShape.SizeFDiagCursor
        return Qt.CursorShape.CrossCursor if self._tool is not None else Qt.CursorShape.ArrowCursor

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if self._state is not OverlayState.ADJUSTING or self._tool is not None:
            return
        if hit_handle(self._rect, self._point(event), self._tol) is Handle.INSIDE:
            self._finish(self._rect)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if self._state is OverlayState.FINISHED:
            return
        if self._editor is not None and event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._close_editor(keep=event.key() != Qt.Key.Key_Escape)  # the editor lost focus; same rules
        elif event.key() == Qt.Key.Key_Escape:
            self._finish(None)
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._confirm()
        elif event.key() == Qt.Key.Key_Delete and self._picked is not None and not self._dragging_mark:
            marks = self._board.marks
            self._board.change(marks[: self._picked] + marks[self._picked + 1 :])
            self._picked = None
            self._marks_changed()
        elif (
            event.key() == Qt.Key.Key_S
            and event.modifiers() == Qt.KeyboardModifier.ControlModifier
            and self.toolbar is not None
        ):
            self._ask_save()  # also from the text editor, which leaves Ctrl+S to us
        elif (
            event.key() == Qt.Key.Key_Z
            and event.modifiers() == Qt.KeyboardModifier.ControlModifier
            and self.toolbar is not None
            and self._drawing is None
        ):
            self._undo()

    # --- painting ----------------------------------------------------------

    def _local_rect(self, rect: Rect) -> QRectF:
        x0, y0 = physical_to_local(self._screen, rect.x, rect.y)
        x1, y1 = physical_to_local(self._screen, rect.x + rect.w, rect.y + rect.h)
        return QRectF(QPointF(x0, y0), QPointF(x1, y1))

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        full = QRectF(self.rect())
        painter.drawImage(full, self._frozen, QRectF(self._frozen.rect()))
        painter.fillRect(full, _DIM)
        if self._rect is not None and self._state is not OverlayState.FINISHED:
            sel = self._local_rect(self._rect)
            source = QRectF(
                self._rect.x - self._screen.physical.x, self._rect.y - self._screen.physical.y, self._rect.w, self._rect.h
            )
            painter.drawImage(sel, self._frozen, source)
            self._paint_marks(painter, sel)
            painter.setPen(QPen(_BORDER, 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(sel)
            if self._state is OverlayState.ADJUSTING and not self._locked:
                self._paint_handles(painter, sel)
            self._paint_size_label(painter)
        painter.end()

    def _paint_size_label(self, painter: QPainter) -> None:
        text, rect = self.size_label
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_LABEL_BACK)
        painter.drawRoundedRect(rect, 3, 3)
        painter.setPen(QColor(255, 255, 255))
        painter.setFont(self._label_font())
        painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), text)

    def _paint_marks(self, painter: QPainter, sel: QRectF) -> None:
        marks = self._board.marks
        if self._moved is not None:
            marks = (*marks[: self._picked], self._moved, *marks[self._picked + 1 :])
        if self._draft is not None:
            marks = (*marks, self._draft)
        if not marks:
            return
        origin = (self._screen.physical.x, self._screen.physical.y)
        painter.save()
        painter.setClipRect(sel)
        painter.scale(1 / self._screen.dpr, 1 / self._screen.dpr)
        painter.translate(-origin[0], -origin[1])
        paint_marks(painter, marks, self._frozen, origin)
        if self._picked is not None:
            b = mark_bounds(marks[self._picked])
            t = self._tol
            painter.setPen(QPen(_BORDER, self._screen.dpr, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QRectF(b.x - t, b.y - t, b.w + 2 * t, b.h + 2 * t))
            if marks[self._picked].tool is Tool.TEXT:
                hx, hy = text_handle(marks[self._picked], t)
                side = HANDLE_SIZE * self._screen.dpr
                painter.fillRect(QRectF(hx - side / 2, hy - side / 2, side, side), _BORDER)
        painter.restore()

    def _paint_handles(self, painter: QPainter, sel: QRectF) -> None:
        painter.setBrush(_BORDER)
        half = HANDLE_SIZE / 2
        xs = (sel.left(), sel.center().x(), sel.right())
        ys = (sel.top(), sel.center().y(), sel.bottom())
        for i, x in enumerate(xs):
            for j, y in enumerate(ys):
                if i == 1 and j == 1:
                    continue
                painter.drawRect(QRectF(x - half, y - half, HANDLE_SIZE, HANDLE_SIZE))


class OverlaySession(QObject):
    """All overlays of one capture; the first result ends the session (emitted once).

    Before ``result`` is emitted, ``marks`` holds the marks of the overlay that
    was confirmed and ``action`` what to do with the picture: ``"copy"``,
    ``"pin"`` when its pin button ended it (M4 plan D10, F15-1), or ``"save"``
    for its save button or Ctrl+S, with the picked file in ``save_path`` (F17-1).
    """

    result = Signal(object)  # Rect, or None when cancelled

    def __init__(self, overlays: list[SelectionOverlay], parent: QObject | None = None) -> None:
        super().__init__(parent)
        if not overlays:
            raise ValueError("a session needs at least one overlay")
        self._overlays = list(overlays)
        self._started = False
        self._finished = False
        self.marks: tuple[Mark, ...] = ()
        self.action = "copy"
        self.save_path: Path | None = None
        for overlay in self._overlays:
            overlay.selected.connect(lambda rect, o=overlay: self._on_selected(o, rect))
            overlay.pinned.connect(lambda rect, o=overlay: self._on_selected(o, rect, "pin"))
            overlay.saved.connect(lambda rect, o=overlay: self._on_selected(o, rect, "save"))
            overlay.cancelled.connect(lambda: self._on_result(None))

    @property
    def finished(self) -> bool:
        return self._finished

    def start(self) -> None:
        if self._started:
            raise RuntimeError("session already started")
        self._started = True
        for overlay in self._overlays:
            overlay.show()
        self._overlays[0].activateWindow()
        self._overlays[0].setFocus()

    def refocus(self) -> None:
        """F18-2: bring the overlays back to the front; the one with a selection (else the first) gets the keys.

        Its save-as dialog, when open, stays on top and gets them instead.
        """
        target = next((o for o in self._overlays if o.selection is not None), self._overlays[0])
        for overlay in self._overlays:
            overlay.raise_()
        dialog = target.save_dialog
        window = dialog if dialog is not None and dialog.isVisible() else target
        window.raise_()
        window.activateWindow()
        window.setFocus()

    def _on_selected(self, overlay: SelectionOverlay, rect: Rect, action: str = "copy") -> None:
        self.marks = overlay.marks
        self.action = action
        self.save_path = overlay.save_path
        self._on_result(rect)

    def _on_result(self, rect: Rect | None) -> None:
        # Exactly once: abandon() makes every overlay inert before anything else can emit.
        self._finished = True
        for overlay in self._overlays:
            overlay.abandon()
            overlay.close()
        self.result.emit(rect)
