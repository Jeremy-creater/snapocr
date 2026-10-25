"""Manual latency measurement (PRD §8). Run only with: python -m pytest -m perf -s

Marked both ``engine`` and ``perf``; the engine lane runs ``engine and not perf``
and the unit lane excludes both, so this never takes part in a gate. If the
median misses the budget, do NOT loosen the assertion: the decision (accept,
or try DirectML) belongs to Jeremy (plan WI-10).
"""

import os
import platform
import statistics
import time
from pathlib import Path

import pytest

from snapocr.engines.config import OcrEngineConfig
from snapocr.engines.rapidocr_engine import RapidOcrEngine

pytestmark = [pytest.mark.engine, pytest.mark.perf]

BUDGET_S = 2.0  # PRD §8, revised from 1.5 s on 2026-10-25 after WI-10 measurement
RUNS = 5
FIXTURE = Path(__file__).parent.parent / "fixtures" / "perf_1080p.png"


def _rss_mb() -> str:
    try:
        import psutil  # optional; not a declared dependency
    except ImportError:
        return "n/a"
    return f"{psutil.Process().memory_info().rss / 2**20:.0f} MB"


def test_1080p_warm_median_under_budget(real_model_paths):
    import onnxruntime

    data = FIXTURE.read_bytes()

    t = time.perf_counter()
    engine = RapidOcrEngine(OcrEngineConfig()).load()
    load_s = time.perf_counter() - t

    t = time.perf_counter()
    first = engine.recognize(data)
    first_s = time.perf_counter() - t

    timings = []
    for _ in range(RUNS):
        t = time.perf_counter()
        engine.recognize(data)
        timings.append(time.perf_counter() - t)
    median_s = statistics.median(timings)

    print(
        f"\n[WI-10] cpu={platform.processor()} cores={os.cpu_count()} "
        f"onnxruntime={onnxruntime.__version__} providers={onnxruntime.get_available_providers()}"
        f"\n[WI-10] load={load_s:.2f}s first={first_s:.2f}s blocks={len(first.blocks)} "
        f"median={median_s:.2f}s max={max(timings):.2f}s runs={[round(x, 2) for x in timings]} "
        f"rss={_rss_mb()}"
    )
    assert len(first.blocks) >= 12, "perf page should yield at least one block per line"
    assert median_s < BUDGET_S, f"warm median {median_s:.2f}s >= budget {BUDGET_S}s"
