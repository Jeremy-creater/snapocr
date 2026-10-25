"""RapidOCR adapter: the only module in snapocr that imports ``rapidocr``.

Heavy runtime deps (rapidocr, onnxruntime, cv2, numpy) are imported lazily
inside methods, so importing this module (or ``snapocr.engines``) stays cheap
and works without them.

Offline guarantee: every model path is passed explicitly, so RapidOCR never
enters its download branch (it downloads when ``model_path`` is None and the
bundled model's SHA does not match). Never pass a ``str`` image to RapidOCR:
it treats strings as file paths or URLs. Never pass ``__call__`` keyword
arguments either: they permanently mutate the instance's state.
"""

from __future__ import annotations

from snapocr.engines.config import (
    _FIX_HINT as FIX_HINT,
    ModelPaths,
    OcrEngineConfig,
    check_model_files,
    resolve_model_paths,
)
from snapocr.engines.convert import output_to_result
from snapocr.engines.errors import EngineLoadError, InvalidImageError, InvalidImageReason
from snapocr.engines.image_check import check_png_bytes
from snapocr.engines.types import OcrResult


def build_rapidocr_params(paths: ModelPaths) -> dict[str, object]:
    """RapidOCR constructor params: explicit local models, no engine-side score filter.

    ``Global.text_score`` is 0.0 so that snapocr's own ``min_score`` is the only
    filter. No ``use_*`` switches: their defaults (det + cls + rec) are wanted.
    """
    return {
        "Det.model_path": str(paths.det),
        "Cls.model_path": str(paths.cls),
        "Rec.model_path": str(paths.rec),
        "Global.text_score": 0.0,
        "Global.log_level": "warning",
    }


class RapidOcrEngine:
    """``OcrEngine`` backed by RapidOCR (in-process, ONNX Runtime, CPU)."""

    def __init__(self, config: OcrEngineConfig) -> None:
        self._config = config
        self._ocr = None

    def load(self) -> RapidOcrEngine:
        """Check the model files, build RapidOCR and create all three sessions now.

        RapidOCR creates its det / cls / rec sessions lazily on first use (cls and
        rec only once text is detected). Forcing them here makes a broken model
        fail in ``load()`` rather than in the middle of a later ``recognize()``.

        Raises ``EngineLoadError`` whose ``model_paths`` names exactly the model
        that failed (the original exception is kept as ``__cause__``).
        """
        paths = resolve_model_paths(self._config)
        check_model_files(paths)

        from rapidocr import RapidOCR

        ocr = RapidOCR(params=build_rapidocr_params(paths))
        # Private loaders of rapidocr 3.10.x (version pinned in pyproject). They
        # only create the sessions and change no recognition settings. Loading
        # them one by one is what lets a failure name the exact broken model.
        for loader, path in (
            (ocr._load_det_model, paths.det),
            (ocr._load_cls_model, paths.cls),
            (ocr._load_rec_model, paths.rec),
        ):
            try:
                loader()
            except Exception as exc:
                raise EngineLoadError(
                    (path,),
                    f"the model file is corrupt or not a usable ONNX model; {FIX_HINT}",
                    detail=f"{type(exc).__name__}: {exc}",
                ) from exc
        self._ocr = ocr
        return self

    def recognize(self, data: bytes) -> OcrResult:
        check_png_bytes(data)

        import cv2
        import numpy as np

        image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise InvalidImageError(InvalidImageReason.DECODE_FAILED, "cv2.imdecode returned no image")

        return output_to_result(self._ocr(image), self._config.min_score)
