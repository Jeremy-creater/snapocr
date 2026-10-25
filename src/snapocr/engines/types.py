"""Engine-agnostic OCR result types and the engine protocol.

Business code depends on these types only; concrete engines (RapidOCR today,
maybe PaddleOCR or a VLM later) convert their native output into them.
This module must stay free of heavy runtime deps (rapidocr, onnxruntime,
numpy, cv2).
"""

from __future__ import annotations

import math
import numbers
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol

Point = tuple[float, float]
Box = tuple[Point, Point, Point, Point]


def _to_finite_float(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise ValueError(f"{field}: expected a real number, got {type(value).__name__}")
    try:
        result = float(value)
    except OverflowError:
        raise ValueError(f"{field}: number too large for float") from None
    if not math.isfinite(result):
        raise ValueError(f"{field}: expected a finite number, got {result!r}")
    return result


def _is_sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _normalize_box(box: object) -> Box:
    if not _is_sequence(box) or len(box) != 4:  # type: ignore[arg-type]
        raise ValueError("box: expected a sequence of exactly 4 points")
    points = []
    for i, point in enumerate(box):  # type: ignore[union-attr]
        if not _is_sequence(point) or len(point) != 2:
            raise ValueError(f"box: point {i} must be a pair (x, y)")
        x, y = point
        points.append(
            (_to_finite_float(x, f"box[{i}].x"), _to_finite_float(y, f"box[{i}].y"))
        )
    return tuple(points)  # type: ignore[return-value]


@dataclass(frozen=True)
class TextBlock:
    """One recognized text region: text, quadrilateral box (4 x (x, y)), score in [0, 1]."""

    text: str
    box: Box
    score: float

    def __post_init__(self) -> None:
        if type(self.text) is not str:
            raise ValueError(f"text: expected str, got {type(self.text).__name__}")
        box = _normalize_box(self.box)
        score = _to_finite_float(self.score, "score")
        if not 0.0 <= score <= 1.0:
            raise ValueError(f"score: expected 0 <= score <= 1, got {score!r}")
        object.__setattr__(self, "box", box)
        object.__setattr__(self, "score", score)


@dataclass(frozen=True)
class OcrResult:
    """Ordered recognition result. Order is the engine's; reading order is not imposed here."""

    blocks: tuple[TextBlock, ...]

    def __post_init__(self) -> None:
        raw: object = self.blocks
        if not isinstance(raw, Iterable) or isinstance(raw, (str, bytes, bytearray)):
            raise ValueError(f"blocks: expected an iterable of TextBlock, got {type(raw).__name__}")
        blocks = tuple(raw)
        for i, block in enumerate(blocks):
            if not isinstance(block, TextBlock):
                raise ValueError(f"blocks[{i}]: expected TextBlock, got {type(block).__name__}")
        object.__setattr__(self, "blocks", blocks)

    @property
    def is_empty(self) -> bool:
        return len(self.blocks) == 0


class OcrEngine(Protocol):
    """Architecture boundary: any OCR backend recognizes PNG bytes into an OcrResult."""

    def recognize(self, data: bytes) -> OcrResult:
        """Recognize text in PNG-encoded image bytes."""
