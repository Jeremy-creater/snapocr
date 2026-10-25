"""WI-13 (T1): collecting the unit lane must not load the OCR runtime (unit lane).

pytest imports every test module during collection, even ones the ``-m``
expression later deselects. So a module-level ``import rapidocr`` in an
engine-lane file would load rapidocr / onnxruntime into every unit run, and
break the unit lane where rapidocr is not installed. The collection runs in an
isolated (``-I``) subprocess so ``sys.modules`` reflects only what it imported.
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UNIT_MARKERS = "not integration and not engine and not perf"
RUNTIME = ["rapidocr", "onnxruntime"]


def test_unit_lane_collection_does_not_import_ocr_runtime():
    code = (
        "import json, sys\n"
        "import pytest\n"
        "class Counter:\n"
        "    collected = None\n"
        "    def pytest_collection_finish(self, session):\n"
        "        Counter.collected = len(session.items)\n"
        "counter = Counter()\n"
        "rc = pytest.main(['--collect-only', '-q', '-p', 'no:cacheprovider',\n"
        f"                 '-m', {UNIT_MARKERS!r}, 'tests'], plugins=[counter])\n"
        f"runtime = {RUNTIME!r}\n"
        "loaded = sorted({m.split('.')[0] for m in sys.modules} & set(runtime))\n"
        "print(json.dumps({'rc': int(rc), 'collected': Counter.collected, 'loaded': loaded}))\n"
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
    out = json.loads(proc.stdout.strip().splitlines()[-1])

    assert out["rc"] == 0
    assert out["collected"] > 0
    assert out["loaded"] == []
