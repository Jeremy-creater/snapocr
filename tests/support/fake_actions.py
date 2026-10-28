"""Scripted OCR engine and translator for the action flows (M2 WI-9, WI-11).

Each fake does one scripted thing per call: return a value or raise an
exception. They never record calls; tests assert on the flows' outputs.
"""

from __future__ import annotations

from dataclasses import dataclass

from snapocr.engines.holder import EngineHolder
from snapocr.engines.types import OcrResult
from snapocr.translators.types import TargetLang, TranslationResult


@dataclass
class ScriptedEngine:
    behaviour: OcrResult | BaseException

    def recognize(self, data: bytes) -> OcrResult:
        if isinstance(self.behaviour, BaseException):
            raise self.behaviour
        return self.behaviour


def holder_for(behaviour: OcrResult | BaseException, *, load_error: BaseException | None = None) -> EngineHolder:
    """A real EngineHolder whose factory either fails with ``load_error`` or builds the engine."""

    def factory() -> ScriptedEngine:
        if load_error is not None:
            raise load_error
        return ScriptedEngine(behaviour)

    return EngineHolder(factory)


@dataclass
class ScriptedTranslator:
    """``behaviour`` is a result, an exception, or "echo".

    "echo" translates s to "T(s)", or to "zh:T(s)" / "en:T(s)" when a target
    is given (F19-6), so the target shows in the output.
    """

    behaviour: TranslationResult | BaseException | str = "echo"

    def translate(self, text: str, target: TargetLang | None = None) -> TranslationResult:
        if isinstance(self.behaviour, BaseException):
            raise self.behaviour
        if self.behaviour == "echo":
            if target is None:
                return TranslationResult(f"T({text})", "en", False)
            return TranslationResult(f"{target}:T({text})", target, False)
        return self.behaviour
