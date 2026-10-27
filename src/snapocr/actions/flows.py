"""The capture, OCR, code OCR, table OCR and translate flows (PRD F7-1 to F7-6, F13-1, F16-1).

Synchronous; run on a worker thread.

Every OCR or translate run yields exactly one ``HistoryRecord`` (F7-6). The
clipboard changes only on success. Only ``OcrError`` and ``TranslationError``
are handled here; anything else propagates to the job runner (WI-11).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from snapocr.actions.messages import (
    NOTHING_TO_TRANSLATE,
    code_ok_notice,
    engine_failed_notice,
    ocr_empty_notice,
    ocr_failed_notice,
    ocr_ok_notice,
    table_ok_notice,
    translation_error_text,
)
from snapocr.actions.outcomes import (
    ClipboardPng,
    ClipboardTable,
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
from snapocr.app import DEFAULT_LOG_DIR, LOG_FILE_NAME
from snapocr.engines.errors import EngineLoadError, OcrError
from snapocr.engines.holder import EngineHolder
from snapocr.engines.types import OcrResult
from snapocr.postprocess import PostprocessOptions, Replacements, postprocess
from snapocr.postprocess.code import code_text
from snapocr.postprocess.table import table_cells, to_html, to_markdown
from snapocr.translators.errors import TranslationError
from snapocr.translators.types import Translator

_log = logging.getLogger(__name__)

# Plan A1: the "raw" OCR text in F10 is layout only, without replacements.
_LAYOUT_ONLY = PostprocessOptions(paragraphs=False, spacing=False, punctuation=False)


@dataclass(frozen=True)
class FlowDeps:
    engine: EngineHolder
    options: PostprocessOptions
    replacements: Replacements
    log_file: Path = DEFAULT_LOG_DIR / LOG_FILE_NAME
    show_text: bool = True


def capture_flow(png: bytes) -> Outcome:
    """F7-1: the PNG goes to the clipboard; no history record."""
    return Outcome(ClipboardPng(png), Notice("已复制截图", ""), None)


def _recognize(png: bytes, deps: FlowDeps) -> OcrResult | Outcome:
    """Load the engine and recognize; an ``Outcome`` when either fails."""
    try:
        engine = deps.engine.get()
    except EngineLoadError as err:
        # F7-4: the full story (paths, fix command, cause) goes to the log; never OCR text.
        _log.warning("OCR engine failed to load: %s", err)
        return Outcome(NoClipboardChange(), engine_failed_notice(err, deps.log_file), HistoryRecord(png, "", "", error=str(err)))
    try:
        return engine.recognize(png)
    except OcrError as err:
        return Outcome(NoClipboardChange(), ocr_failed_notice(err), HistoryRecord(png, "", "", error=str(err)))


def _ocr(png: bytes, deps: FlowDeps, *, code: bool = False) -> OcrStage | Outcome:
    """OCR and post-processing; an ``Outcome`` when the run ends here (error or empty).

    ``code``: the text is the F13 code layout instead of the F2 chain (no replacements).
    """
    result = _recognize(png, deps)
    if isinstance(result, Outcome):
        return result
    raw = postprocess(result, _LAYOUT_ONLY)
    text = code_text(result) if code else postprocess(result, deps.options, deps.replacements)
    if not text:
        return Outcome(NoClipboardChange(), ocr_empty_notice(), HistoryRecord(png, raw, text))
    return OcrStage(png, raw, text)


def ocr_flow(png: bytes, deps: FlowDeps) -> Outcome:
    """F7-2 to F7-4: the post-processed text goes to the clipboard."""
    stage = _ocr(png, deps)
    if isinstance(stage, Outcome):
        return stage
    notice = ocr_ok_notice(stage.text, deps.show_text)
    return Outcome(ClipboardText(stage.text), notice, HistoryRecord(png, stage.raw, stage.text))


def code_ocr_flow(png: bytes, deps: FlowDeps) -> Outcome:
    """F13-1: the code text goes to the clipboard; empty and failed runs end like ``ocr_flow``."""
    stage = _ocr(png, deps, code=True)
    if isinstance(stage, Outcome):
        return stage
    notice = code_ok_notice(stage.text, deps.show_text)
    return Outcome(ClipboardText(stage.text), notice, HistoryRecord(png, stage.raw, stage.text))


def table_ocr_flow(png: bytes, deps: FlowDeps) -> Outcome:
    """F16-1, F16-2: the table goes to the clipboard as HTML and Markdown (no replacements; plan D23).

    No cell left (nothing recognized, or only spreadsheet letters) ends like an empty OCR.
    """
    result = _recognize(png, deps)
    if isinstance(result, Outcome):
        return result
    raw = postprocess(result, _LAYOUT_ONLY)
    cells = table_cells(result)
    if not cells:
        return Outcome(NoClipboardChange(), ocr_empty_notice(), HistoryRecord(png, raw, ""))
    markdown = to_markdown(cells)
    return Outcome(
        ClipboardTable(markdown, to_html(cells)),
        table_ok_notice(len(cells), len(cells[0])),
        HistoryRecord(png, raw, markdown),
    )


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
