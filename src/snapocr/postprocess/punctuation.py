"""F2-2 half-width to full-width punctuation in Chinese context (plan WI-5, matrix Q8 / Q9 / Q16).

``to_fullwidth_punctuation`` works on *runs*: maximal stretches of ``,;:?!.``.
A run is judged as a whole and is converted (``,;:?!`` to ``，；：？！`` and
``.`` to ``。``) iff the nearest non-space character to its left or right is a
Han character (``chars.is_cjk``). Only U+0020 and ``\t`` are skipped when
looking for that neighbour, and the search never crosses ``\n``.

A run is left unchanged when:

- it contains ``..`` (ellipsis-like dot runs);
- any of its characters lies inside a protected span (``spans.protected_spans``);
- it contains ``.``, its left neighbour is Han and the character immediately
  after the run is an ASCII letter or digit (``文件.txt``; this direction only);
- it starts at the ``.`` of a line-start list number
  ``^[ \t]*[0-9]{1,3}.`` that is not followed by a digit (``1. 支持``).

"Both neighbours are ASCII digits" (``3.14``, ``1,000``) needs no separate
check: a digit is never Han, so such a run has no Han neighbour.

After a run is converted, all consecutive U+0020 / ``\t`` directly on both sides
of it are deleted.
"""

import re

from snapocr.postprocess.chars import is_cjk, is_latin_alnum
from snapocr.postprocess.spans import protected_spans

_FULLWIDTH = str.maketrans({",": "，", ";": "；", ":": "：", "?": "？", "!": "！", ".": "。"})
_RUN = re.compile(r"[,;:?!.]+")
_LIST_DOT = re.compile(r"^[ \t]*[0-9]{1,3}(\.)(?![0-9])", re.MULTILINE)
_SKIP = " \t"


def _nearest(text: str, i: int, step: int) -> str | None:
    """First character from ``i`` in direction ``step`` that is not a space or tab, on this line."""
    while 0 <= i < len(text) and text[i] in _SKIP:
        i += step
    if 0 <= i < len(text) and text[i] != "\n":
        return text[i]
    return None


def _is_han(c: str | None) -> bool:
    return c is not None and is_cjk(c)


def _should_convert(text: str, start: int, end: int, protected: list[bool], list_dots: set[int]) -> bool:
    run = text[start:end]
    if ".." in run or any(protected[start:end]) or start in list_dots:
        return False
    left_han = _is_han(_nearest(text, start - 1, -1))
    if not (left_han or _is_han(_nearest(text, end, 1))):
        return False
    return not ("." in run and left_han and end < len(text) and is_latin_alnum(text[end]))


def to_fullwidth_punctuation(text: str) -> str:
    """Return ``text`` with ASCII marks in Chinese context replaced by full-width ones."""
    if not isinstance(text, str):
        raise TypeError(f"expected str, got {type(text).__name__}")
    protected = [False] * len(text)
    for start, end in protected_spans(text):
        protected[start:end] = [True] * (end - start)
    list_dots = {m.start(1) for m in _LIST_DOT.finditer(text)}
    out = []
    pos = 0
    for m in _RUN.finditer(text):
        start, end = m.span()
        if not _should_convert(text, start, end, protected, list_dots):
            continue
        left = start
        while left > pos and text[left - 1] in _SKIP:
            left -= 1
        right = end
        while right < len(text) and text[right] in _SKIP:
            right += 1
        out.append(text[pos:left])
        out.append(m.group().translate(_FULLWIDTH))
        pos = right
    out.append(text[pos:])
    return "".join(out)
