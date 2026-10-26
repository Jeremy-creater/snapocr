"""WI-8 U4: real-service translator tests are collected only by their own lanes."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EXPRESSIONS = {
    "unit": "not integration and not engine and not perf",
    "engine": "engine and not perf",
    "integration": "integration and not perf",
    "perf": "perf",
}
REAL = "tests/translators/test_ollama_real.py"
INTEGRATION_IDS = [
    f"{REAL}::test_real_zh_to_en",
    f"{REAL}::test_real_en_to_zh",
    f"{REAL}::test_real_model_not_found",
    f"{REAL}::test_real_response_shape_contract",
    f"{REAL}::test_real_truncated_by_max_tokens",
    f"{REAL}::test_real_no_text_in_logs",
    f"{REAL}::test_real_loopback_only",
]
EXPECTED = {
    REAL: {"unit": [], "engine": [], "integration": INTEGRATION_IDS, "perf": []},
}


def _collect(path: str) -> dict[str, list[str]]:
    code = (
        "import json, pytest\n"
        "class Ids:\n"
        "    def __init__(self): self.ids = []\n"
        "    def pytest_collection_finish(self, session):\n"
        "        self.ids = [item.nodeid for item in session.items]\n"
        f"exprs = {EXPRESSIONS!r}\n"
        "out = {}\n"
        "for lane, expr in exprs.items():\n"
        "    ids = Ids()\n"
        f"    pytest.main(['--collect-only', '-q', '-p', 'no:cacheprovider', '-m', expr, {path!r}],\n"
        "                plugins=[ids])\n"
        "    out[lane] = ids.ids\n"
        "print(json.dumps(out))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-I", "-c", code],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
    )
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
    return json.loads(proc.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("path", list(EXPECTED))
def test_translator_lane_markers(path):
    collected = _collect(path)
    for lane, expected in EXPECTED[path].items():
        assert sorted(collected[lane]) == sorted(expected), lane
