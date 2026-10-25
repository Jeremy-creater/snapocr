r"""Protected spans for F2 post-processing (plan WI-1, matrix Q5).

``protected_spans`` finds URLs, e-mail addresses, backtick code and Windows
paths. The spacing and punctuation rules leave every character inside these
spans untouched.

Q5 rules:

- URL: from ``https?://`` or ``www.`` up to whitespace or full-width
  punctuation (Han characters are included), then trailing ASCII
  ``.,;:!?)`` is stripped.
- Windows path: from ``[A-Za-z]:\`` with the same end rule.
- E-mail: ``[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}``.
- Backtick code: a closed pair on one line; an unclosed backtick is nothing.
- Overlapping spans merge; spans that only touch stay separate.
"""

import re

from snapocr.postprocess.chars import is_cjk_punct

_TRAILING = ".,;:!?)"
_RUN_START = re.compile(r"https?://|www\.|[A-Za-z]:\\")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_BACKTICK = re.compile(r"`[^`\n]+`")


def _run_end(text: str, trigger_end: int) -> int:
    """End of a URL / path run whose trigger ends at ``trigger_end``.

    Trailing ASCII punctuation is stripped, but never into the trigger itself.
    """
    end = trigger_end
    while end < len(text) and not (text[end].isspace() or is_cjk_punct(text[end])):
        end += 1
    while end > trigger_end and text[end - 1] in _TRAILING:
        end -= 1
    return end


def _url_and_path_spans(text: str) -> list[tuple[int, int]]:
    spans = []
    pos = 0
    while (m := _RUN_START.search(text, pos)) is not None:
        end = _run_end(text, m.end())
        spans.append((m.start(), end))
        # The run reaches the next whitespace / full-width punctuation (minus
        # stripped ASCII punctuation, which cannot start a trigger), so no
        # trigger is skipped by resuming here.
        pos = end
    return spans


def protected_spans(text: str) -> tuple[tuple[int, int], ...]:
    """Sorted, non-overlapping ``(start, end)`` intervals that must not be rewritten."""
    if not isinstance(text, str):
        raise TypeError(f"expected str, got {type(text).__name__}")
    found = _url_and_path_spans(text)
    found += [m.span() for m in _EMAIL.finditer(text)]
    found += [m.span() for m in _BACKTICK.finditer(text)]
    merged: list[tuple[int, int]] = []
    for start, end in sorted(found):
        if merged and start < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return tuple(merged)
