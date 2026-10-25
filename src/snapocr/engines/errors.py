"""Engine-agnostic OCR exception hierarchy.

Must stay free of heavy runtime deps (rapidocr, onnxruntime, numpy, cv2).
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from enum import Enum


class OcrError(Exception):
    """Base class for every OCR-layer error."""


class InvalidImageReason(Enum):
    NOT_BYTES = "input is not bytes"
    EMPTY = "input is empty"
    NOT_PNG = "input is not a PNG image"
    TRUNCATED = "PNG data is truncated"
    DECODE_FAILED = "image could not be decoded"


class InvalidImageError(OcrError):
    """The input image was rejected before or during decoding."""

    def __init__(self, reason: InvalidImageReason, detail: str = "") -> None:
        self.reason = reason
        self.detail = detail
        message = f"invalid image [{reason.name}]: {reason.value}"
        if detail:
            message = f"{message} ({detail})"
        super().__init__(message)


class EngineLoadError(OcrError):
    """The OCR engine could not be loaded; lists the offending model files and a fix."""

    def __init__(
        self,
        model_paths: Iterable[str | os.PathLike[str]],
        hint: str,
        *,
        detail: str = "",
    ) -> None:
        self.model_paths = tuple(model_paths)
        self.hint = hint
        self.detail = detail
        listed = "; ".join(os.fspath(p) for p in self.model_paths)
        message = f"failed to load OCR engine; model files: {listed}; fix: {hint}"
        if detail:
            message = f"{message}; cause: {detail}"
        super().__init__(message)


class EngineRuntimeError(OcrError):
    """The engine was loaded but failed or produced malformed output while recognizing."""
