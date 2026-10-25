"""Character classifiers for F2 post-processing (plan WI-1, matrix Q6 / Q16).

Each classifier takes exactly one character: a non-``str`` argument raises
``TypeError`` and a string whose length is not 1 raises ``ValueError``.
"""

# Q6: full-width punctuation ranges (inclusive) plus a few general-punctuation
# characters used in Chinese text. U+3000 (ideographic space), full-width
# letters and full-width digits are deliberately excluded.
_CJK_PUNCT_RANGES = (
    (0x3001, 0x303F),
    (0xFF01, 0xFF0F),
    (0xFF1A, 0xFF20),
    (0xFF3B, 0xFF40),
    (0xFF5B, 0xFF65),
)
_CJK_PUNCT_EXTRA = frozenset("“”‘’…—")


def _code_point(c: object) -> int:
    if not isinstance(c, str):
        raise TypeError(f"expected a single-character str, got {type(c).__name__}")
    if len(c) != 1:
        raise ValueError(f"expected a single character, got a string of length {len(c)}")
    return ord(c)


def is_cjk(c: str) -> bool:
    """Han ideograph: CJK Unified Ideographs or Extension A."""
    o = _code_point(c)
    return 0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF


def is_cjk_punct(c: str) -> bool:
    """Full-width (CJK) punctuation, per Q6."""
    o = _code_point(c)
    return c in _CJK_PUNCT_EXTRA or any(lo <= o <= hi for lo, hi in _CJK_PUNCT_RANGES)


def is_latin_alnum(c: str) -> bool:
    """ASCII letter or digit, ``[A-Za-z0-9]``."""
    o = _code_point(c)
    return o < 0x80 and c.isalnum()
