"""Screenshot annotation model (PRD F14, F15; M4 plan D6, D8). Stdlib only.

Marks live in physical virtual-desktop pixels, like ``Rect``. Sizes (stroke
width, font size) are turned into physical pixels when a mark is made, using
the dpr of the screen it is drawn on, so an exported image needs no dpr.
Drawing is ``snapocr.gui.marks_paint``; this module never imports Qt.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from snapocr.geometry import Point, Rect


class Tool(Enum):
    RECT = "rect"
    ELLIPSE = "ellipse"
    ARROW = "arrow"
    TEXT = "text"


PALETTE = ("#e53935", "#fb8c00", "#fdd835", "#43a047", "#1e88e5", "#8e24aa", "#000000", "#ffffff")
COLOR_NAMES = ("红", "橙", "黄", "绿", "蓝", "紫", "黑", "白")
WIDTH_LEVELS = (2, 4, 6)  # stroke width, logical px (F14-4)
FONT_LEVELS = (14, 20, 28)  # text size, logical px
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
    """One annotation. ``size`` is in physical px: stroke width, or font size for text."""

    tool: Tool
    points: tuple[Point, ...]
    color: str
    size: int
    text: str = ""


def scaled(value: float, dpr: float) -> int:
    """A logical size in physical pixels, rounded half up, at least 1."""
    return max(1, math.floor(value * dpr + 0.5))


_BOX_TOOLS = (Tool.RECT, Tool.ELLIPSE)


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
    return Mark(tool, pts, style.color, scaled(WIDTH_LEVELS[style.level], dpr))


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

    def undo(self) -> bool:
        if not self._past:
            return False
        self._marks = self._past.pop()
        return True


def arrow_head(
    start: Point, end: Point, width: int
) -> tuple[tuple[float, float], tuple[tuple[float, float], tuple[float, float], tuple[float, float]]]:
    """The shaft's end and the head triangle (tip, left, right) of an arrow from ``start`` to ``end``.

    The head is ``max(10, 4 * width)`` long, or the whole arrow when that is
    shorter, and as wide as it is long; the shaft stops at its base so a
    thick line never pokes out of the tip.
    """
    length = math.dist(start, end)
    if length == 0:
        raise ValueError("an arrow needs a length > 0")
    head = min(length, max(10, 4 * width))
    ux, uy = (end[0] - start[0]) / length, (end[1] - start[1]) / length
    bx, by = end[0] - ux * head, end[1] - uy * head
    half = head / 2
    tip = (float(end[0]), float(end[1]))
    return (bx, by), (tip, (bx - uy * half, by + ux * half), (bx + uy * half, by - ux * half))


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
