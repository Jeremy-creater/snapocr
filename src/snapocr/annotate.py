"""Screenshot annotation model (PRD F14, F15; M4 plan D6, D8). Stdlib only.

Marks live in physical virtual-desktop pixels, like ``Rect``. Sizes (stroke
width, font size) are turned into physical pixels when a mark is made, using
the dpr of the screen it is drawn on, so an exported image needs no dpr.
Drawing is ``snapocr.gui.marks_paint``; this module never imports Qt.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from enum import Enum

from snapocr.geometry import Point, Rect


class Tool(Enum):
    RECT = "rect"
    ELLIPSE = "ellipse"
    ARROW = "arrow"
    TEXT = "text"
    NUMBER = "number"
    PEN = "pen"
    MOSAIC = "mosaic"


PALETTE = ("#e53935", "#fb8c00", "#fdd835", "#43a047", "#1e88e5", "#8e24aa", "#000000", "#ffffff")
COLOR_NAMES = ("红", "橙", "黄", "绿", "蓝", "紫", "黑", "白")
WIDTH_LEVELS = (2, 4, 6)  # stroke width, logical px (F14-4)
FONT_LEVELS = (14, 20, 28)  # text size, logical px
NUMBER_LEVELS = (20, 28, 36)  # number badge diameter, logical px (F14-8)
MOSAIC_LEVELS = (8, 12, 16)  # mosaic block side, logical px (F14-8)
LEVEL_NAMES = ("细", "中", "粗")
MIN_DRAG = 3  # physical px: a shorter drag leaves no mark (F14-2)


@dataclass(frozen=True)
class Style:
    """The colour and size level the next mark is drawn with."""

    color: str = PALETTE[0]
    level: int = 1

    def __post_init__(self) -> None:
        if self.color not in PALETTE:
            raise ValueError(f"color must be one of the palette, got {self.color!r}")
        if type(self.level) is not int or not 0 <= self.level < len(WIDTH_LEVELS):
            raise ValueError(f"level must be 0, 1 or 2, got {self.level!r}")


DEFAULT_STYLE = Style()


@dataclass(frozen=True)
class Mark:
    """One annotation. ``size`` is in physical px: stroke width, font size for
    text, badge diameter for a number (whose ``text`` is the number), block
    side for a mosaic."""

    tool: Tool
    points: tuple[Point, ...]
    color: str
    size: int
    text: str = ""


def scaled(value: float, dpr: float) -> int:
    """A logical size in physical pixels, rounded half up, at least 1."""
    return max(1, math.floor(value * dpr + 0.5))


_BOX_TOOLS = (Tool.RECT, Tool.ELLIPSE, Tool.MOSAIC)


def drag_mark(tool: Tool, start: Point, end: Point, style: Style, dpr: float) -> Mark | None:
    """The mark a drag from ``start`` to ``end`` draws; ``None`` when it is too short."""
    if tool not in (*_BOX_TOOLS, Tool.ARROW):
        raise ValueError(f"{tool.value} is not drawn by dragging")
    if max(abs(end[0] - start[0]), abs(end[1] - start[1])) < MIN_DRAG:
        return None
    if tool in _BOX_TOOLS:
        pts = ((min(start[0], end[0]), min(start[1], end[1])), (max(start[0], end[0]), max(start[1], end[1])))
    else:
        pts = (start, end)
    levels = MOSAIC_LEVELS if tool is Tool.MOSAIC else WIDTH_LEVELS
    return Mark(tool, pts, style.color, scaled(levels[style.level], dpr))


_LEVEL_TABLES = {Tool.TEXT: FONT_LEVELS, Tool.NUMBER: NUMBER_LEVELS, Tool.MOSAIC: MOSAIC_LEVELS}


def with_level(mark: Mark, level: int, dpr: float) -> Mark:
    """``mark`` at the size of ``level`` for its tool (F14-10); a text box is re-measured by the GUI."""
    if type(level) is not int or not 0 <= level < len(WIDTH_LEVELS):
        raise ValueError(f"level must be 0, 1 or 2, got {level!r}")
    return replace(mark, size=scaled(_LEVEL_TABLES.get(mark.tool, WIDTH_LEVELS)[level], dpr))


def next_number(marks: Iterable[Mark]) -> int:
    """One more than the largest number mark, or 1 (F14-8: undo makes it go back)."""
    return max((int(m.text) for m in marks if m.tool is Tool.NUMBER), default=0) + 1


def number_mark(center: Point, marks: Iterable[Mark], style: Style, dpr: float) -> Mark:
    """The next number badge, centred on ``center``."""
    size = scaled(NUMBER_LEVELS[style.level], dpr)
    return Mark(Tool.NUMBER, (center,), style.color, size, str(next_number(marks)))


def pen_mark(points: Sequence[Point], style: Style, dpr: float) -> Mark | None:
    """A freehand stroke through ``points``; repeated points dropped; ``None`` if it never
    gets ``MIN_DRAG`` px away from where it started."""
    kept: list[Point] = []
    for p in points:
        if not kept or p != kept[-1]:
            kept.append(p)
    if not kept:
        return None
    x0, y0 = kept[0]
    if max(max(abs(x - x0), abs(y - y0)) for x, y in kept) < MIN_DRAG:
        return None
    return Mark(Tool.PEN, tuple(kept), style.color, scaled(WIDTH_LEVELS[style.level], dpr))


_STROKED = (Tool.RECT, Tool.ELLIPSE, Tool.PEN)


def mark_bounds(mark: Mark) -> Rect:
    """The box a mark covers, in physical px (strokes included; a number is its badge)."""
    if mark.tool is Tool.NUMBER:
        (cx, cy), r = mark.points[0], mark.size / 2
        x0, y0, x1, y1 = math.floor(cx - r), math.floor(cy - r), math.ceil(cx + r), math.ceil(cy + r)
    elif mark.tool is Tool.ARROW:
        shape = arrow_shape(mark.points[0], mark.points[1], mark.size)
        xs, ys = [x for x, _ in shape], [y for _, y in shape]
        x0, y0, x1, y1 = math.floor(min(xs)), math.floor(min(ys)), math.ceil(max(xs)), math.ceil(max(ys))
    else:
        xs, ys = [x for x, _ in mark.points], [y for _, y in mark.points]
        pad = math.ceil(mark.size / 2) if mark.tool in _STROKED else 0
        x0, y0, x1, y1 = min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad
    return Rect(x0, y0, x1 - x0, y1 - y0)


def hit_mark(marks: Sequence[Mark], p: Point, tol: int) -> int | None:
    """Index of the topmost mark whose box, grown by ``tol``, holds ``p`` (F14-8)."""
    for i in range(len(marks) - 1, -1, -1):
        b = mark_bounds(marks[i])
        if b.x - tol <= p[0] <= b.x + b.w + tol and b.y - tol <= p[1] <= b.y + b.h + tol:
            return i
    return None


def moved(mark: Mark, dx: int, dy: int) -> Mark:
    return replace(mark, points=tuple((x + dx, y + dy) for x, y in mark.points))


class Board:
    """The marks of one capture, with snapshot undo (F14-6)."""

    def __init__(self) -> None:
        self._marks: tuple[Mark, ...] = ()
        self._past: list[tuple[Mark, ...]] = []

    @property
    def marks(self) -> tuple[Mark, ...]:
        return self._marks

    @property
    def can_undo(self) -> bool:
        return bool(self._past)

    def add(self, mark: Mark) -> None:
        self._past.append(self._marks)
        self._marks = (*self._marks, mark)

    def change(self, marks: tuple[Mark, ...]) -> None:
        """Replace all marks at once (a move or a delete); one undo step."""
        self._past.append(self._marks)
        self._marks = marks

    def undo(self) -> bool:
        if not self._past:
            return False
        self._marks = self._past.pop()
        return True


FloatPoint = tuple[float, float]


def arrow_shape(start: Point, end: Point, width: int) -> tuple[FloatPoint, ...]:
    """The filled outline of an arrow from ``start`` to ``end`` (F14-9, plan D16).

    Six points: the sharp tail (``start``), the left of the neck, the left
    wing, the tip (``end``), the right wing, the right of the neck. The neck
    is ``length / 20`` wide, kept within ``width`` .. ``3 * width``; the head
    is three necks long (at most half the arrow) and 1.2 times as wide as it
    is long. Long arrows come out bolder.
    """
    length = math.dist(start, end)
    if length == 0:
        raise ValueError("an arrow needs a length > 0")
    neck = min(max(width, length / 20), 3 * width)
    head = min(3 * neck, length / 2)
    wing, half = 0.6 * head, min(neck / 2, 0.3 * head)
    ux, uy = (end[0] - start[0]) / length, (end[1] - start[1]) / length
    bx, by = end[0] - ux * head, end[1] - uy * head
    px, py = -uy, ux  # left of the direction

    def side(d: float) -> FloatPoint:
        return (bx + px * d, by + py * d)

    tail, tip = (float(start[0]), float(start[1])), (float(end[0]), float(end[1]))
    return (tail, side(half), side(wing), tip, side(-wing), side(-half))


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(v, hi))


def toolbar_place(sel: Rect, size: tuple[int, int], area: Rect, gap: int) -> tuple[int, int]:
    """Top-left of the annotation toolbar (F14-1): below, else above, else inside; within ``area``."""
    w, h = size
    bottom = area.y + area.h
    x = _clamp(sel.x + sel.w - w, area.x, area.x + area.w - w)
    below = sel.y + sel.h + gap
    if below + h <= bottom:
        return x, below
    above = sel.y - gap - h
    if above >= area.y:
        return x, above
    return x, _clamp(sel.y + sel.h - gap - h, area.y, bottom - h)


ZOOM_MIN, ZOOM_MAX, ZOOM_STEP = 10, 500, 10  # pinned-image zoom, percent (F15-2)


def zoom_percent(current: int, steps: int) -> int:
    """The zoom after ``steps`` wheel notches (negative: smaller), within the limits."""
    return max(ZOOM_MIN, min(current + steps * ZOOM_STEP, ZOOM_MAX))


def _half_up(v: float) -> int:
    return math.floor(v + 0.5)


def zoom_rect(rect: Rect, anchor: tuple[float, float], base: tuple[int, int], percent: int) -> Rect:
    """``rect`` resized to ``percent`` of ``base``, keeping ``anchor`` at the same place inside it."""
    w = max(1, _half_up(base[0] * percent / 100))
    h = max(1, _half_up(base[1] * percent / 100))
    fx, fy = (anchor[0] - rect.x) / rect.w, (anchor[1] - rect.y) / rect.h
    return Rect(_half_up(anchor[0] - fx * w), _half_up(anchor[1] - fy * h), w, h)
