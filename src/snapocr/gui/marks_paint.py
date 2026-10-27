"""Draw annotation marks (PRD F14-7; M4 plan D6, D7).

One function draws for both the overlay preview and the exported image, so
they cannot drift apart. The painter works in physical virtual-desktop
pixels: the overlay scales by 1/dpr and moves to its screen's origin first;
``render_marked`` moves to the image's origin.
"""

from __future__ import annotations

from collections.abc import Sequence

import math

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QImage, QPainter, QPainterPath, QPen, QPolygonF

from snapocr.annotate import FONT_LEVELS, Mark, Style, Tool, arrow_head, scaled
from snapocr.geometry import Point

TEXT_FAMILY = "Microsoft YaHei UI"
_LIGHT = ("#fdd835", "#ffffff")  # badge colours that need dark digits
NUMBER_FONT_RATIO = 0.55  # digit height relative to the badge diameter


def text_font(size: int) -> QFont:
    """The font of a text mark; ``size`` is its pixel size."""
    font = QFont(TEXT_FAMILY)
    font.setPixelSize(size)
    return font


def text_mark(text: str, top_left: Point, style: Style, dpr: float) -> Mark | None:
    """A text mark at ``top_left`` (physical); its second point is the far corner of the text (plan D9).

    Leading and trailing blanks are dropped; nothing left gives ``None`` (F14-5).
    """
    text = text.strip()
    if not text:
        return None
    size = scaled(FONT_LEVELS[style.level], dpr)
    metrics = QFontMetrics(text_font(size))
    far = (top_left[0] + metrics.horizontalAdvance(text), top_left[1] + metrics.height())
    return Mark(Tool.TEXT, (top_left, far), style.color, size, text)


def _box(mark: Mark) -> QRectF:
    (x0, y0), (x1, y1) = mark.points
    return QRectF(QPointF(x0, y0), QPointF(x1, y1))


def _mosaic(painter: QPainter, mark: Mark, base: QImage, origin: Point) -> None:
    """Pixelate the box: each ``size`` px block gets the average colour of ``base`` under it.

    Blocks start at the box's top-left corner. Only the part of the box that
    lies on ``base`` is drawn.
    """
    (x0, y0), (x1, y1) = mark.points
    box = QRect(x0 - origin[0], y0 - origin[1], x1 - x0, y1 - y0).intersected(base.rect())
    if box.isEmpty():
        return
    b = mark.size
    # Whole blocks from the box corner that cover the visible part.
    left = box.x() - (box.x() - (x0 - origin[0])) % b
    top = box.y() - (box.y() - (y0 - origin[1])) % b
    cols = math.ceil((box.right() + 1 - left) / b)
    rows = math.ceil((box.bottom() + 1 - top) / b)
    grid = QRect(left, top, cols * b, rows * b).intersected(base.rect())
    small = base.copy(grid).scaled(
        math.ceil(grid.width() / b),
        math.ceil(grid.height() / b),
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    blocks = small.scaled(small.width() * b, small.height() * b)  # nearest: hard block edges
    painter.save()
    painter.setClipRect(box.translated(origin[0], origin[1]), Qt.ClipOperation.IntersectClip)
    painter.drawImage(QPoint(grid.x() + origin[0], grid.y() + origin[1]), blocks)
    painter.restore()


def _paint(painter: QPainter, mark: Mark, base: QImage, origin: Point) -> None:
    color = QColor(mark.color)
    pen = QPen(color, mark.size, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.MiterJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    if mark.tool is Tool.MOSAIC:
        _mosaic(painter, mark, base, origin)
    elif mark.tool is Tool.RECT:
        painter.drawRect(_box(mark))
    elif mark.tool is Tool.ELLIPSE:
        painter.drawEllipse(_box(mark))
    elif mark.tool is Tool.ARROW:
        start, end = mark.points
        shaft_end, head = arrow_head(start, end, mark.size)
        painter.drawLine(QPointF(*start), QPointF(*shaft_end))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawPolygon(QPolygonF([QPointF(*p) for p in head]))
    elif mark.tool is Tool.NUMBER:
        (cx, cy), r = mark.points[0], mark.size / 2
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawEllipse(QPointF(cx, cy), r, r)
        font = text_font(max(1, round(mark.size * NUMBER_FONT_RATIO)))
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#000000" if mark.color in _LIGHT else "#ffffff"))
        painter.drawText(QRectF(cx - r, cy - r, mark.size, mark.size), int(Qt.AlignmentFlag.AlignCenter), mark.text)
    elif mark.tool is Tool.PEN:
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        path = QPainterPath(QPointF(*mark.points[0]))
        for p in mark.points[1:]:
            path.lineTo(QPointF(*p))
        painter.drawPath(path)
    else:  # Tool.TEXT
        painter.setFont(text_font(mark.size))
        painter.drawText(_box(mark), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop), mark.text)


def paint_marks(painter: QPainter, marks: Sequence[Mark], base: QImage, origin: Point) -> None:
    """Draw ``marks`` in order with ``painter`` (physical coordinates).

    ``base`` is the picture under the marks and ``origin`` the physical
    position of its top-left pixel (used by marks that read pixels).
    """
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    for mark in marks:
        _paint(painter, mark, base, origin)
    painter.restore()


def render_marked(image: QImage, marks: Sequence[Mark], origin: Point) -> QImage:
    """A copy of ``image`` (top-left pixel at physical ``origin``) with ``marks`` drawn on it."""
    out = image.copy()
    if marks:
        painter = QPainter(out)
        painter.translate(-origin[0], -origin[1])
        paint_marks(painter, marks, image, origin)
        painter.end()
    return out
