"""Convert RapidOCR-shaped raw output into an engine-agnostic OcrResult.

Pure logic: does not import rapidocr or numpy. numpy arrays are handled by
duck typing (``.tolist()``), which also turns numpy scalars into Python floats.
"""

from __future__ import annotations

from snapocr.engines.errors import EngineRuntimeError
from snapocr.engines.types import OcrResult, TextBlock


def _plain(value: object) -> object:
    tolist = getattr(value, "tolist", None)
    return tolist() if callable(tolist) else value


def to_result(boxes: object, txts: object, scores: object, min_score: float) -> OcrResult:
    """Build an OcrResult from parallel boxes / txts / scores.

    All three None means "no text found" and yields an empty result. Blocks with
    ``score < min_score`` or whitespace-only text are dropped; kept text is
    verbatim. Engine order is preserved. Malformed output raises
    EngineRuntimeError.
    """
    raw = {"boxes": boxes, "txts": txts, "scores": scores}
    missing = [name for name, value in raw.items() if value is None]
    if len(missing) == len(raw):
        return OcrResult(())
    if missing:
        raise EngineRuntimeError(f"incomplete engine output: {', '.join(missing)} is None")

    box_list, txt_list, score_list = (list(_plain(v)) for v in raw.values())  # type: ignore[call-overload]
    if not len(box_list) == len(txt_list) == len(score_list):
        raise EngineRuntimeError(
            "engine output length mismatch: "
            f"boxes={len(box_list)}, txts={len(txt_list)}, scores={len(score_list)}"
        )

    kept = []
    for i, (box, text, score) in enumerate(zip(box_list, txt_list, score_list)):
        try:
            block = TextBlock(text=text, box=box, score=score)
        except ValueError as exc:
            raise EngineRuntimeError(f"malformed engine output at block {i}: {exc}") from exc
        if block.score >= min_score and block.text.strip():
            kept.append(block)
    return OcrResult(tuple(kept))
