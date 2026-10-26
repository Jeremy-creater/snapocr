"""Translation direction (F4-1, D1).

``cjk / (cjk + latin) >= threshold`` translates to English, otherwise to
Chinese. Written as a division, not ``cjk >= threshold * total``: ``0.7 * 10``
is ``7.000000000000001`` in floating point and would flip the boundary.
Text with neither Han characters nor ASCII letters has no direction (``None``).
"""

from __future__ import annotations

import math
import numbers
import string

from snapocr.postprocess.chars import is_cjk
from snapocr.translators.config import TranslatorConfig
from snapocr.translators.types import TargetLang

_LATIN = frozenset(string.ascii_letters)


def count_scripts(text: str) -> tuple[int, int]:
    """(Han characters, ASCII letters). Digits, punctuation, full-width letters etc. don't count."""
    if not isinstance(text, str):
        raise TypeError(f"text: expected str, got {type(text).__name__}")
    cjk = latin = 0
    for c in text:
        if c in _LATIN:
            latin += 1
        elif is_cjk(c):
            cjk += 1
    return cjk, latin


def detect_target_lang(text: str, threshold: float) -> TargetLang | None:
    if (
        isinstance(threshold, bool)
        or not isinstance(threshold, numbers.Real)
        or not math.isfinite(threshold)
        or not 0 < threshold <= 1
    ):
        raise ValueError("threshold: expected a finite number with 0 < t <= 1")
    cjk, latin = count_scripts(text)
    total = cjk + latin
    if total == 0:
        return None
    return "en" if cjk / total >= threshold else "zh"


def resolve_target(text: str, config: TranslatorConfig) -> TargetLang | None:
    """A fixed ``target_lang`` wins, even for text without letters (D1)."""
    if config.target_lang != "auto":
        return config.target_lang  # type: ignore[return-value]
    return detect_target_lang(text, config.direction_threshold)
