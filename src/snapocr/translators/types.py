"""Translation result type and the translator protocol (F4).

Business code (``snapocr.actions``) depends on these only. Stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

TargetLang = Literal["zh", "en"]
_TARGETS = ("zh", "en", None)


@dataclass(frozen=True)
class TranslationResult:
    """``skipped`` is True exactly when no model was called (``target_lang is None``)."""

    text: str
    target_lang: TargetLang | None
    skipped: bool

    def __post_init__(self) -> None:
        if type(self.text) is not str:
            raise TypeError(f"text: expected str, got {type(self.text).__name__}")
        if type(self.skipped) is not bool:
            raise TypeError(f"skipped: expected bool, got {type(self.skipped).__name__}")
        if self.target_lang not in _TARGETS:
            raise ValueError("target_lang: expected 'zh', 'en' or None")
        if self.skipped != (self.target_lang is None):
            raise ValueError("skipped must be True exactly when target_lang is None")


@runtime_checkable
class Translator(Protocol):
    def translate(self, text: str) -> TranslationResult: ...
