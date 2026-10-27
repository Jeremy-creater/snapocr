"""F2-0 layout: group OCR blocks into reading-order lines (plan WI-2).

``build_lines`` turns an engine-ordered ``OcrResult`` into lines, independent
of the input block order:

1. Each block is reduced to the bounding rectangle of its 4 points. Characters
   that ``str.splitlines`` treats as line boundaries become U+0020, then the
   text is stripped; whitespace-only blocks are dropped (Q3).
2. Blocks are visited in a total order starting with the vertical center. A
   block joins the current line iff its vertical overlap with the line's
   *median* vertical range is at least ``SAME_LINE_OVERLAP`` times the smaller
   of the two heights. When that smaller height is 0 this means the closed
   ranges touch, i.e. the zero-height block's y lies inside the other (Q4).
3. Within a line blocks are ordered by ``left`` (ties broken by the remaining
   coordinates, then ``(text, score)``) and joined with the Q11 seam rule.
4. A line's ``top`` / ``bottom`` are the medians of its blocks' tops /
   bottoms; ``left`` / ``right`` are the min / max (Q2).
5. ``gap_before`` is set when ``next.top - prev.bottom`` is strictly greater
   than ``PARAGRAPH_GAP`` times the median line height; never on the first
   line and never when the median line height is 0.

All thresholds are ratios of heights, so results do not depend on the
absolute image size. The constants are calibrated by plan WI-8.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from statistics import median

from snapocr.engines.types import OcrResult
from snapocr.postprocess.chars import is_cjk, is_cjk_punct

SAME_LINE_OVERLAP = 0.5
PARAGRAPH_GAP = 1.5

# Q3: every character str.splitlines() treats as a line boundary.
_LINE_BREAKS = str.maketrans(dict.fromkeys("\n\r\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029", " "))


@dataclass(frozen=True)
class Line:
    """One reading-order line: joined text, bounding coordinates, paragraph-gap flag."""

    text: str
    left: float
    right: float
    top: float
    bottom: float
    gap_before: bool


def _tight(c: str) -> bool:
    return is_cjk(c) or is_cjk_punct(c)


def seam_join(left: str, right: str) -> str:
    """Join two non-empty texts with the Q11 seam rule.

    No separator when the character on either side of the seam is a Han
    ideograph or full-width punctuation; otherwise one U+0020.
    """
    if _tight(left[-1]) or _tight(right[0]):
        return left + right
    return left + " " + right


# A normalized block: (center_y, top, bottom, left, right, text, score). The
# tuple order is the total order used for line assignment, so equal tuples are
# indistinguishable in the output.
_Block = tuple[float, float, float, float, float, str, float]


def _normalize(result: OcrResult) -> list[_Block]:
    blocks: list[_Block] = []
    for block in result.blocks:
        text = block.text.translate(_LINE_BREAKS).strip()
        if not text:
            continue
        xs = [x for x, _ in block.box]
        ys = [y for _, y in block.box]
        top, bottom = min(ys), max(ys)
        blocks.append(((top + bottom) / 2, top, bottom, min(xs), max(xs), text, block.score))
    blocks.sort()
    return blocks


def _same_line(top: float, bottom: float, line_top: float, line_bottom: float) -> bool:
    overlap = min(bottom, line_bottom) - max(top, line_top)
    return overlap >= SAME_LINE_OVERLAP * min(bottom - top, line_bottom - line_top)


def _group(blocks: list[_Block]) -> list[list[_Block]]:
    groups: list[list[_Block]] = []
    for block in blocks:
        if groups:
            current = groups[-1]
            line_top = median(b[1] for b in current)
            line_bottom = median(b[2] for b in current)
            if _same_line(block[1], block[2], line_top, line_bottom):
                current.append(block)
                continue
        groups.append([block])
    return groups


def group_blocks(result: OcrResult) -> list[list[_Block]]:
    """Steps 1 and 2 of the module doc: normalized blocks grouped into lines, top to bottom.

    Each block is ``(center_y, top, bottom, left, right, text, score)``; the
    blocks of a line are in the step-2 order, not sorted by ``left``. Shared
    with the F13 code layout (``postprocess.code``).
    """
    return _group(_normalize(result))


def _make_line(group: list[_Block]) -> Line:
    members = sorted(group, key=lambda b: (b[3], b[1], b[2], b[4], b[5], b[6]))
    text = members[0][5]
    for b in members[1:]:
        text = seam_join(text, b[5])
    return Line(
        text=text,
        left=min(b[3] for b in group),
        right=max(b[4] for b in group),
        top=median(b[1] for b in group),
        bottom=median(b[2] for b in group),
        gap_before=False,
    )


def build_lines(result: OcrResult) -> tuple[Line, ...]:
    """Group the blocks of ``result`` into reading-order lines (see module doc)."""
    if not isinstance(result, OcrResult):
        raise TypeError(f"expected OcrResult, got {type(result).__name__}")
    lines = [_make_line(g) for g in group_blocks(result)]
    if not lines:
        return ()
    line_height = median(line.bottom - line.top for line in lines)
    threshold = PARAGRAPH_GAP * line_height
    out = [lines[0]]
    for prev, line in zip(lines, lines[1:]):
        gap = line_height > 0 and line.top - prev.bottom > threshold
        out.append(replace(line, gap_before=gap))
    return tuple(out)
