"""F2-3 paragraph merging and line output (plan WI-3, matrix Q1/Q7/Q10/Q11/Q16).

``merge_paragraphs`` merges line i into the previous line (the current group's
last line) iff ALL of these hold:

1. line i has ``gap_before == False``;
2. the previous line does not end with sentence-end punctuation
   ``。！？!?.：:；;…`` optionally followed by any number of closing chars
   ``」』”’"'）)】》〉`` (closing chars alone are not a sentence end);
3. the previous line is full:
   ``right - region_left >= full_ratio * (region_right - region_left)``;
4. line i is not a list item (``- `` / ``* ``, ``•`` / ``·``, ``1.`` ``1)``
   ``1、`` not followed by a digit, ``(1)``, ``（1）``, circled 1-20, ``一、``).

``region`` defaults to ``(min left, max right)`` of the input; callers that
need idempotence pass one fixed region (Q1). A merged line keeps ``left`` /
``top`` / ``gap_before`` of its first line and ``right`` / ``bottom`` of its
last. Texts are joined with the Q11 seam rule, except that no separator is
added when the previous text ends with an ASCII letter followed by ``-``.

``lines_to_text`` joins line texts with LF and puts an empty line before every
line at index > 0 whose ``gap_before`` is set (Q10).
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import replace
from string import ascii_letters

from snapocr.postprocess.layout import Line, seam_join

_SENTENCE_END = re.compile("[\u3002\uff01\uff1f!?.\uff1a:\uff1b;\u2026][\u300d\u300f\u201d\u2019\"'\uff09)\u3011\u300b\u3009]*$")
_LIST_ITEM = re.compile(
    r"[-*]\s"
    "|[\u2022\u00b7]"
    r"|[0-9]{1,3}[.)\u3001](?![0-9])"
    r"|\([0-9]{1,3}\)"
    "|\uff08[0-9]{1,3}\uff09"
    "|[\u2460-\u2473]"
    "|[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341]+\u3001"
)


def _check_lines(lines: object) -> tuple[Line, ...]:
    if isinstance(lines, (str, bytes)) or not isinstance(lines, Sequence):
        raise TypeError(f"expected a sequence of Line, got {type(lines).__name__}")
    for line in lines:
        if not isinstance(line, Line):
            raise TypeError(f"expected Line items, got {type(line).__name__}")
    return tuple(lines)


def _join(left: str, right: str) -> str:
    if len(left) >= 2 and left[-1] == "-" and left[-2] in ascii_letters:
        return left + right
    return seam_join(left, right)


def merge_paragraphs(
    lines: Sequence[Line],
    *,
    full_ratio: float = 0.85,
    region: tuple[float, float] | None = None,
) -> tuple[Line, ...]:
    """Merge wrapped lines into paragraphs (see module doc)."""
    lines = _check_lines(lines)
    if isinstance(full_ratio, bool) or not isinstance(full_ratio, (int, float)):
        raise TypeError(f"full_ratio must be a number, got {type(full_ratio).__name__}")
    if not (math.isfinite(full_ratio) and 0 < full_ratio <= 1):
        raise ValueError(f"full_ratio must be finite and in (0, 1], got {full_ratio!r}")
    if not lines:
        return ()
    if region is None:
        region = (min(line.left for line in lines), max(line.right for line in lines))
    region_left, region_right = region
    threshold = full_ratio * (region_right - region_left)
    out = [lines[0]]
    for line in lines[1:]:
        prev = out[-1]
        if (
            not line.gap_before
            and _SENTENCE_END.search(prev.text) is None
            and prev.right - region_left >= threshold
            and _LIST_ITEM.match(line.text) is None
        ):
            out[-1] = replace(prev, text=_join(prev.text, line.text), right=line.right, bottom=line.bottom)
        else:
            out.append(line)
    return tuple(out)


def lines_to_text(lines: Sequence[Line]) -> str:
    """LF-join line texts, with an empty line before each gap line at index > 0."""
    parts: list[str] = []
    for i, line in enumerate(_check_lines(lines)):
        if i and line.gap_before:
            parts.append("")
        parts.append(line.text)
    return "\n".join(parts)
