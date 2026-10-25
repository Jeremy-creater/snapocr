"""Engine-lane precondition: the real model files must exist, or the run FAILS.

Never skip: a skipped engine lane would report green with nothing verified.
"""

from __future__ import annotations

import pytest

from snapocr.engines.config import ModelPaths


def require_model_files(paths: ModelPaths) -> ModelPaths:
    bad = []
    for path in (paths.det, paths.cls, paths.rec):
        if not path.is_file():
            bad.append(f"{path} (missing)")
        elif path.stat().st_size == 0:
            bad.append(f"{path} (empty)")
    if bad:
        pytest.fail(
            "engine lane needs the real RapidOCR model files; problems: "
            + "; ".join(bad)
            + r". Fix: uv pip install --python D:\DevLocal\envs\snapocr\Scripts\python.exe"
            " --reinstall rapidocr==3.10.0",
            pytrace=False,
        )
    return paths
