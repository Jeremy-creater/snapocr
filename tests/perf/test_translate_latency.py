"""Manual translation latency measurement (PRD §8, F4 WI-9).

Run only with: python -m pytest -m perf -s tests/perf/test_translate_latency.py
Marked ``integration`` and ``perf``; the integration lane runs
``integration and not perf``, so this never takes part in a gate. Needs
Ollama with hy-mt2:7b (``require_ollama`` fails otherwise). If the median
misses the budget, do NOT loosen the assertion: the decision belongs to Jeremy.
"""

import http.client
import json
import statistics
import time
from pathlib import Path

import pytest

from snapocr.translators import OpenAICompatTranslator, TranslatorConfig

pytestmark = [pytest.mark.integration, pytest.mark.perf, pytest.mark.usefixtures("require_ollama")]

BUDGET_S = 3.0  # PRD §8: 200 characters in under 3 s with the model loaded
RUNS = 5
FIXTURE = Path(__file__).parent.parent / "fixtures" / "translators" / "perf_zh_200.txt"


def _ollama_version(config: TranslatorConfig) -> str:
    conn = http.client.HTTPConnection(config.endpoint.host, config.endpoint.port, timeout=5)
    try:
        conn.request("GET", "/api/version")
        return json.loads(conn.getresponse().read()).get("version", "?")
    except (OSError, ValueError):
        return "?"
    finally:
        conn.close()


def test_translate_200_chars_warm_median_under_budget():
    text = FIXTURE.read_text(encoding="utf-8").strip()
    assert 150 <= len(text) <= 200
    config = TranslatorConfig()
    translator = OpenAICompatTranslator(config)

    def timed() -> float:
        start = time.perf_counter()
        result = translator.translate(text)
        elapsed = time.perf_counter() - start
        assert result.target_lang == "en"
        assert result.skipped is False
        assert result.text
        return elapsed

    first = timed()  # warm-up; includes a cold model load if Ollama had unloaded it
    samples = sorted(timed() for _ in range(RUNS))
    median = statistics.median(samples)
    p95 = samples[min(len(samples) - 1, round(0.95 * (len(samples) - 1)))]
    print(
        f"\n[translate perf] chars={len(text)} model={config.model} "
        f"ollama={_ollama_version(config)} first={first:.2f}s "
        f"median={median:.2f}s p95={p95:.2f}s runs={[round(s, 2) for s in samples]}"
    )
    assert median < BUDGET_S
