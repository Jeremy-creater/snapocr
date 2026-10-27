"""F13 code OCR layout (M3 WI-13): keep line breaks, indentation and blank lines.

``code_text`` turns an ``OcrResult`` into code text. Lines are grouped exactly
as in F2-0 (``layout.group_blocks``); none of the F2 prose rules run.

1. Character width ``cw``: the median of ``width / len(text)`` over blocks of
   at least 3 characters (all blocks when there are none). A zero width means
   no indentation and one space between blocks.
2. Within a line, blocks are joined left to right with
   ``max(1, round(gap / cw))`` spaces (F13-2).
3. Each line's offset from the leftmost line, in characters, is ``c``. The
   unit is 4 when at least half of the lines with ``c >= 1`` round to a
   multiple of 4, else 2; the indentation is ``round(c / unit) * unit``
   spaces (F13-3). Offsets are noisy by up to about half a character, so
   rounding to the unit (never below 2) absorbs it.
4. The pitch is the median of the positive top-to-top distances between
   neighbouring lines; ``round(distance / pitch) - 1`` blank lines go between
   two lines (F13-4).

Rounding is half up throughout (not Python's banker's rounding).
"""

from __future__ import annotations

import math
from statistics import median

from snapocr.engines.types import OcrResult
from snapocr.postprocess.layout import group_blocks

# Blocks shorter than this give a poor character width (one wide "}" or "x").
_MIN_WIDTH_CHARS = 3


def _half_up(x: float) -> int:
    return math.floor(x + 0.5)


def code_text(result: OcrResult) -> str:
    """The code text of ``result`` (see module doc)."""
    groups = group_blocks(result)
    if not groups:
        return ""
    blocks = [b for g in groups for b in g]
    widths = [(b[4] - b[3]) / len(b[5]) for b in blocks]
    long_widths = [w for b, w in zip(blocks, widths) if len(b[5]) >= _MIN_WIDTH_CHARS]
    # x / inf == 0: a zero width turns every offset and gap into 0 columns.
    cw = median(long_widths or widths) or math.inf

    lines = []  # (left, top, text)
    for group in groups:
        members = sorted(group, key=lambda b: (b[3], b[4]))
        text = members[0][5]
        for prev, block in zip(members, members[1:]):
            text += " " * max(1, _half_up((block[3] - prev[4]) / cw)) + block[5]
        lines.append((members[0][3], median(b[1] for b in group), text))

    x0 = min(left for left, _, _ in lines)
    cols = [(left - x0) / cw for left, _, _ in lines]
    indented = [_half_up(c) for c in cols if c >= 1]
    unit = 4 if indented and sum(n % 4 == 0 for n in indented) * 2 >= len(indented) else 2

    steps = [b[1] - a[1] for a, b in zip(lines, lines[1:])]
    pitch = median([s for s in steps if s > 0] or [math.inf])

    out = []
    for i, ((_, _, text), c) in enumerate(zip(lines, cols)):
        if i:
            out.extend([""] * max(0, _half_up(steps[i - 1] / pitch) - 1))
        out.append(" " * (_half_up(c / unit) * unit) + text)
    return "\n".join(out)
