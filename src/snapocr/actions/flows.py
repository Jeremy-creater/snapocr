"""The capture, OCR and translate flows (PRD F7-1 to F7-6). Synchronous; run on a worker thread.

Every OCR or translate run yields exactly one ``HistoryRecord`` (F7-6). The
clipboard changes only on success. Only ``OcrError`` and ``TranslationError``
are handled here; anything else propagates to the job runner (WI-11).
"""

from __future__ import annotations

from dataclasses import dataclass

from snapocr.actions.messages import (
    NOTHING_TO_TRANSLATE,
    engine_failed_notice,
    ocr_empty_notice,
    ocr_failed_notice,
    ocr_ok_notice,
    translation_error_text,
)
from snapocr.actions.outcomes import (
    ClipboardPng,
    ClipboardText,
    Done,
    Failed,
    HistoryRecord,
    NoClipboardChange,
    Notice,
    OcrStage,
    Outcome,
    TranslateOutcome,
)
from snapocr.engines.errors import EngineLoadError, OcrError
from snapocr.engines.holder import EngineHolder
from snapocr.postprocess import PostprocessOptions, Replacements, postprocess
from snapocr.translators.errors import TranslationError
from snapocr.translators.types import Translator

# Plan A1: the "raw" OCR text in F10 is layout only, without replacements.
_LAYOUT_ONLY = PostprocessOptions(paragraphs=False, spacing=False, punctuation=False)


@dataclass(frozen=True)
class FlowDeps:
    engine: EngineHolder
    options: PostprocessOptions
    replacements: Replacements


def capture_flow(png: bytes) -> Outcome:
    """F7-1: the PNG goes to the clipboard; no history record."""
    return Outcome(ClipboardPng(png), Notice("已复制截图", ""), None)


def _ocr(png: bytes, deps: FlowDeps) -> OcrStage | Outcome:
    """OCR and post-processing; an ``Outcome`` when the run ends here (error or empty)."""
    try:
        engine = deps.engine.get()
    except EngineLoadError as err:
        return Outcome(NoClipboardChange(), engine_failed_notice(err), HistoryRecord(png, "", "", error=str(err)))
    try:
        result = engine.recognize(png)
    except OcrError as err:
        return Outcome(NoClipboardChange(), ocr_failed_notice(err), HistoryRecord(png, "", "", error=str(err)))
    raw = postprocess(result, _LAYOUT_ONLY)
    text = postprocess(result, deps.options, deps.replacements)
    if not text:
        return Outcome(NoClipboardChange(), ocr_empty_notice(), HistoryRecord(png, raw, text))
    return OcrStage(png, raw, text)


def ocr_flow(png: bytes, deps: FlowDeps) -> Outcome:
    """F7-2 to F7-4: the post-processed text goes to the clipboard."""
    stage = _ocr(png, deps)
    if isinstance(stage, Outcome):
        return stage
    return Outcome(ClipboardText(stage.text), ocr_ok_notice(stage.text), HistoryRecord(png, stage.raw, stage.text))


def translate_ocr_stage(png: bytes, deps: FlowDeps) -> OcrStage | Outcome:
    """First half of F7-5; an empty or failed OCR ends like the OCR action (plan A4)."""
    return _ocr(png, deps)


def translate_stage(stage: OcrStage, translator: Translator) -> TranslateOutcome:
    """Second half of F7-5: translate the post-processed text (plan A2)."""
    try:
        result = translator.translate(stage.text)
    except TranslationError as err:
        message = translation_error_text(err)
        return TranslateOutcome(
            NoClipboardChange(),
            Failed(stage.text, message),
            HistoryRecord(stage.png, stage.raw, stage.text, error=message),
        )
    if result.skipped:  # plan A3
        return TranslateOutcome(
            NoClipboardChange(),
            Failed(stage.text, NOTHING_TO_TRANSLATE),
            HistoryRecord(stage.png, stage.raw, stage.text, error=NOTHING_TO_TRANSLATE),
        )
    return TranslateOutcome(
        ClipboardText(result.text),
        Done(stage.text, result.text),
        HistoryRecord(stage.png, stage.raw, stage.text, translation=result.text),
    )
