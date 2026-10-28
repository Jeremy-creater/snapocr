"""Screen and selection geometry (PRD F6-2 to F6-5). Stdlib only.

Physical pixels are integers in the virtual-desktop coordinates that GDI uses.
Overlay windows report local logical coordinates (floats, per screen). A Rect's
edges are coordinate lines: ``Rect(0, 0, 4, 4)`` covers pixels 0..3.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

Point = tuple[int, int]

# Qt rounds a screen's logical size; allow that much slack when pairing (F6-2).
_SIZE_SLACK = 1.0


class ScreenMismatch(ValueError):
    """Qt's screens and the Win32 monitors cannot be paired."""


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    w: int
    h: int

    def __post_init__(self) -> None:
        if not all(_is_int(v) for v in (self.x, self.y, self.w, self.h)):
            raise ValueError(f"Rect fields must be int, got {self!r}")
        if self.w < 0 or self.h < 0:
            raise ValueError(f"Rect size must be >= 0, got {self!r}")


@dataclass(frozen=True)
class ScreenInfo:
    name: str
    logical: Rect
    dpr: float
    physical: Rect

    def __post_init__(self) -> None:
        dpr = self.dpr
        if isinstance(dpr, bool) or not isinstance(dpr, (int, float)) or not math.isfinite(dpr) or dpr <= 0:
            raise ValueError(f"dpr must be a finite number > 0, got {dpr!r}")


class Handle(Enum):
    NONE = "none"
    INSIDE = "inside"
    NW = "nw"
    NE = "ne"
    SW = "sw"
    SE = "se"
    N = "n"
    S = "s"
    W = "w"
    E = "e"


def match_screens(
    qt_screens: Sequence[tuple[str, Rect, float]], monitors: Sequence[tuple[str, Rect]]
) -> list[ScreenInfo]:
    """Pair Qt screens with Win32 monitors by device name, in Qt's order."""
    qt_names = [name for name, _, _ in qt_screens]
    by_name = dict(monitors)
    if len(set(qt_names)) != len(qt_names) or len(by_name) != len(monitors):
        raise ScreenMismatch(f"duplicate screen names: Qt {qt_names}, monitors {[n for n, _ in monitors]}")
    if set(qt_names) != set(by_name):
        raise ScreenMismatch(f"screen names differ: Qt {sorted(qt_names)}, monitors {sorted(by_name)}")
    result = []
    for name, logical, dpr in qt_screens:
        screen = ScreenInfo(name, logical, dpr, by_name[name])
        p = screen.physical
        if abs(p.w / dpr - logical.w) > _SIZE_SLACK or abs(p.h / dpr - logical.h) > _SIZE_SLACK:
            raise ScreenMismatch(f"{name}: physical {p.w}x{p.h} at dpr {dpr} != logical {logical.w}x{logical.h}")
        result.append(screen)
    return result


def _round(v: float) -> int:
    return math.floor(v + 0.5)


def local_to_physical(screen: ScreenInfo, x: float, y: float) -> Point:
    """Overlay-local logical coordinates to physical virtual-desktop pixels."""
    p = screen.physical
    return p.x + _round(x * screen.dpr), p.y + _round(y * screen.dpr)


def physical_to_local(screen: ScreenInfo, px: int, py: int) -> tuple[float, float]:
    p = screen.physical
    return (px - p.x) / screen.dpr, (py - p.y) / screen.dpr


def _clamp(v: int, lo: int, hi: int) -> int:
    return min(max(v, lo), hi)


def _span_rect(screen: ScreenInfo, x0: int, y0: int, x1: int, y1: int) -> Rect:
    """Normalise two edge pairs and clip them to the screen."""
    s = screen.physical
    xa, xb = sorted((_clamp(x0, s.x, s.x + s.w), _clamp(x1, s.x, s.x + s.w)))
    ya, yb = sorted((_clamp(y0, s.y, s.y + s.h), _clamp(y1, s.y, s.y + s.h)))
    return Rect(xa, ya, xb - xa, yb - ya)


def selection_rect(screen: ScreenInfo, p0: Point, p1: Point) -> Rect:
    """The rectangle dragged from p0 to p1 (either direction), clipped to the screen."""
    return _span_rect(screen, p0[0], p0[1], p1[0], p1[1])


def is_cancel_size(rect: Rect) -> bool:
    """F6-3: smaller than 4x4 physical pixels counts as cancel."""
    return rect.w < 4 or rect.h < 4


def crop_box(rect: Rect, virtual_origin: Point) -> Rect:
    """Where ``rect`` lies inside a virtual-desktop image whose top-left is ``virtual_origin``."""
    return Rect(rect.x - virtual_origin[0], rect.y - virtual_origin[1], rect.w, rect.h)


# Tie-break orders when several handles are equally near (tiny or thin selections).
_CORNERS = (Handle.SE, Handle.SW, Handle.NE, Handle.NW)
_EDGES = (Handle.S, Handle.E, Handle.N, Handle.W)


def hit_handle(rect: Rect, p: Point, tol: int) -> Handle:
    """Which part of the selection a press at ``p`` grabs (F6-5).

    Corners (Chebyshev distance <= tol) beat edges (distance <= tol within the
    edge's span), which beat the interior. Among equals the nearest wins.
    """
    if tol < 0:
        raise ValueError(f"tol must be >= 0, got {tol!r}")
    px, py = p
    x0, y0, x1, y1 = rect.x, rect.y, rect.x + rect.w, rect.y + rect.h
    corner_pos = {Handle.SE: (x1, y1), Handle.SW: (x0, y1), Handle.NE: (x1, y0), Handle.NW: (x0, y0)}
    corners = [(max(abs(px - cx), abs(py - cy)), h) for h, (cx, cy) in corner_pos.items()]
    best = _nearest(corners, tol, _CORNERS)
    if best is not None:
        return best
    in_x = x0 <= px <= x1
    in_y = y0 <= py <= y1
    edges = []
    if in_x:
        edges += [(abs(py - y1), Handle.S), (abs(py - y0), Handle.N)]
    if in_y:
        edges += [(abs(px - x1), Handle.E), (abs(px - x0), Handle.W)]
    best = _nearest(edges, tol, _EDGES)
    if best is not None:
        return best
    return Handle.INSIDE if in_x and in_y else Handle.NONE


def _nearest(candidates: list[tuple[int, Handle]], tol: int, order: tuple[Handle, ...]) -> Handle | None:
    hits = [(d, order.index(h), h) for d, h in candidates if d <= tol]
    return min(hits)[2] if hits else None


def resize(rect: Rect, handle: Handle, p: Point, screen: ScreenInfo) -> Rect:
    """Move the grabbed edge(s) to ``p``; passing the opposite edge flips the box (F6-5)."""
    if handle in (Handle.NONE, Handle.INSIDE):
        raise ValueError(f"{handle} is not an edge or corner")
    x0, y0, x1, y1 = rect.x, rect.y, rect.x + rect.w, rect.y + rect.h
    px, py = p
    if handle in (Handle.NW, Handle.W, Handle.SW):
        x0 = px
    if handle in (Handle.NE, Handle.E, Handle.SE):
        x1 = px
    if handle in (Handle.NW, Handle.N, Handle.NE):
        y0 = py
    if handle in (Handle.SW, Handle.S, Handle.SE):
        y1 = py
    return _span_rect(screen, x0, y0, x1, y1)


def move(rect: Rect, dx: int, dy: int, screen: ScreenInfo) -> Rect:
    """Shift by (dx, dy), stopping at the screen edges; the size never changes (F6-5)."""
    s = screen.physical
    if not (s.x <= rect.x and s.y <= rect.y and rect.x + rect.w <= s.x + s.w and rect.y + rect.h <= s.y + s.h):
        raise ValueError(f"{rect} is not inside screen {screen.name} {s}")
    return Rect(
        _clamp(rect.x + dx, s.x, s.x + s.w - rect.w),
        _clamp(rect.y + dy, s.y, s.y + s.h - rect.h),
        rect.w,
        rect.h,
    )


def place_popup(anchor: Rect, size: tuple[int, int], available: Rect, gap: int = 8) -> Rect:
    """Where the result popup goes (F8-1), in logical screen coordinates.

    The popup is first shrunk to ``available``. It goes below the selection,
    else above, else to the right, else to the left; below and above are
    left-aligned with the selection, right and left top-aligned, then shifted
    inside ``available``. If none fits it is pushed inside and may overlap.
    """
    if not (_is_int(size[0]) and _is_int(size[1])) or min(size) < 0:
        raise ValueError(f"size must be two ints >= 0, got {size!r}")
    if not _is_int(gap) or gap < 0:
        raise ValueError(f"gap must be an int >= 0, got {gap!r}")
    av = available
    w, h = min(size[0], av.w), min(size[1], av.h)
    left = _clamp(anchor.x, av.x, av.x + av.w - w)
    top = _clamp(anchor.y, av.y, av.y + av.h - h)
    candidates = [
        (left, anchor.y + anchor.h + gap),  # below
        (left, anchor.y - gap - h),  # above
        (anchor.x + anchor.w + gap, top),  # right
        (anchor.x - gap - w, top),  # left
    ]
    for x, y in candidates:
        if av.x <= x and av.y <= y and x + w <= av.x + av.w and y + h <= av.y + av.h:
            return Rect(x, y, w, h)
    return Rect(left, _clamp(anchor.y + anchor.h + gap, av.y, av.y + av.h - h), w, h)


def fit_size(src: tuple[int, int], max_box: tuple[int, int]) -> tuple[int, int]:
    """Scale ``src`` down to fit ``max_box``, keeping the aspect ratio; never enlarge (F10-1)."""
    if not all(_is_int(v) and v > 0 for v in (*src, *max_box)):
        raise ValueError(f"sizes must be ints > 0, got {src!r} and {max_box!r}")
    sw, sh = src
    mw, mh = max_box
    if sw <= mw and sh <= mh:
        return sw, sh
    if sw * mh >= sh * mw:  # width is the limit
        return mw, max(1, _round_ratio(sh * mw, sw))
    return max(1, _round_ratio(sw * mh, sh)), mh


def _round_ratio(num: int, den: int) -> int:
    """num / den rounded half up, in exact integer arithmetic."""
    return (2 * num + den) // (2 * den)


def screen_containing(rect: Rect, screens: Sequence[ScreenInfo]) -> ScreenInfo:
    """The screen whose physical rect holds all of ``rect`` (a selection never spans screens, D4)."""
    for screen in screens:
        p = screen.physical
        if p.x <= rect.x and p.y <= rect.y and rect.x + rect.w <= p.x + p.w and rect.y + rect.h <= p.y + p.h:
            return screen
    raise ValueError(f"no screen holds {rect}")


def logical_rect(screen: ScreenInfo, rect: Rect) -> Rect:
    """``rect`` (physical, on ``screen``) in Qt's global logical coordinates, rounded outwards (F8-1)."""
    x0, y0 = physical_to_local(screen, rect.x, rect.y)
    x1, y1 = physical_to_local(screen, rect.x + rect.w, rect.y + rect.h)
    left, top = math.floor(x0), math.floor(y0)
    return Rect(screen.logical.x + left, screen.logical.y + top, math.ceil(x1) - left, math.ceil(y1) - top)


def size_text(rect: Rect) -> str:
    """F18-6: the selection size shown next to it, e.g. "1280 × 720" (physical pixels)."""
    return f"{rect.w} × {rect.h}"


def label_place(sel: Rect, size: tuple[int, int], bounds: Rect, gap: int) -> tuple[int, int]:
    """F18-6: top-left of the size label (logical px): above ``sel``, left-aligned; inside at its top if not.

    ``x`` stays inside ``bounds`` left and right.
    """
    w, h = size
    x = max(bounds.x, min(sel.x, bounds.x + bounds.w - w))
    y = sel.y - gap - h
    if y < bounds.y:
        y = sel.y + gap
    return x, y



def center_in(size: tuple[int, int], available: Rect) -> Rect:
    """F19-3: ``size`` shrunk to ``available`` and centred in it (logical coordinates)."""
    if not (_is_int(size[0]) and _is_int(size[1])) or min(size) < 0:
        raise ValueError(f"size must be two ints >= 0, got {size!r}")
    w, h = min(size[0], available.w), min(size[1], available.h)
    return Rect(available.x + (available.w - w) // 2, available.y + (available.h - h) // 2, w, h)
