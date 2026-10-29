"""OCR engine configuration and local model-file resolution.

Locates the RapidOCR bundled models via ``importlib.util.find_spec`` without
executing ``import rapidocr``. Must stay free of heavy runtime deps
(rapidocr, onnxruntime, numpy, cv2).
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path

from snapocr.engines.errors import EngineLoadError

DET_MODEL = "PP-OCRv6_det_small.onnx"
CLS_MODEL = "ch_ppocr_mobile_v2.0_cls_mobile.onnx"
REC_MODEL = "PP-OCRv6_rec_small.onnx"

RELEASES_URL = "https://github.com/Jeremy-creater/snapocr/releases"
_MODEL_DIR_HINT = "or set `model_dir` in the config to a directory holding the models"


def fix_hint(executable: str, frozen: bool) -> str:
    """How to get the models back: reinstall rapidocr with this Python (PRD F21-4), or, in the
    packaged build that has no pip, download and unzip snapocr again (F22-3)."""
    if frozen:
        return f"download snapocr again from {RELEASES_URL} and unzip it, {_MODEL_DIR_HINT}"
    return f'run `"{executable}" -m pip install --force-reinstall rapidocr==3.10.0`, {_MODEL_DIR_HINT}'


_FIX_HINT = fix_hint(sys.executable, getattr(sys, "frozen", False))


@dataclass(frozen=True)
class OcrEngineConfig:
    min_score: float = 0.5
    model_dir: Path | None = None

    def __post_init__(self) -> None:
        # nan fails both comparisons; no math.isnan, which overflows on huge TOML ints (FIX-1).
        if not 0.0 <= self.min_score <= 1.0:
            raise ValueError(f"min_score must be within [0, 1], got {self.min_score!r}")


@dataclass(frozen=True)
class ModelPaths:
    det: Path
    cls: Path
    rec: Path


def _default_model_dir() -> Path:
    spec = importlib.util.find_spec("rapidocr")
    if spec is None:
        raise EngineLoadError((), f"rapidocr is not installed; {_FIX_HINT}")
    return Path(spec.origin).parent / "models"


def resolve_model_paths(config: OcrEngineConfig) -> ModelPaths:
    model_dir = Path(config.model_dir) if config.model_dir is not None else _default_model_dir()
    return ModelPaths(
        det=model_dir / DET_MODEL,
        cls=model_dir / CLS_MODEL,
        rec=model_dir / REC_MODEL,
    )


def _is_usable(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 0


def check_model_files(paths: ModelPaths) -> None:
    bad = [p for p in (paths.det, paths.cls, paths.rec) if not _is_usable(p)]
    if bad:
        raise EngineLoadError(bad, f"missing, empty or not a file; {_FIX_HINT}")
