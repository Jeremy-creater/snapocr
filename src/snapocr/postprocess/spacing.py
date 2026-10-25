"""F2-1 CJK / Latin spacing (plan WI-4, matrix Q16).

``add_cjk_latin_spacing`` inserts one U+0020 between a Han character
(``chars.is_cjk``) and an ASCII letter or digit (``chars.is_latin_alnum``) that
are directly adjacent, in either order, unless both characters lie inside the
same protected span (``spans.protected_spans``). Any character in between --
whitespace (including U+3000), a newline, punctuation -- means the pair is not
adjacent, so nothing is ever inserted across a line break. Only spaces are
inserted; nothing is removed.
"""

from snapocr.postprocess.chars import is_cjk, is_latin_alnum
from snapocr.postprocess.spans import protected_spans


def _is_mixed_pair(a: str, b: str) -> bool:
    return (is_cjk(a) and is_latin_alnum(b)) or (is_latin_alnum(a) and is_cjk(b))


def add_cjk_latin_spacing(text: str) -> str:
    """Return ``text`` with a space between each adjacent Han | Latin-alnum pair."""
    if not isinstance(text, str):
        raise TypeError(f"expected str, got {type(text).__name__}")
    # span_id[i] is the index of the protected span containing character i, or -1.
    span_id = [-1] * len(text)
    for k, (start, end) in enumerate(protected_spans(text)):
        span_id[start:end] = [k] * (end - start)
    out = []
    for i, c in enumerate(text):
        if i > 0 and _is_mixed_pair(text[i - 1], c) and (span_id[i] == -1 or span_id[i] != span_id[i - 1]):
            out.append(" ")
        out.append(c)
    return "".join(out)
