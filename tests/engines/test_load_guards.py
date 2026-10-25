"""WI-7: load() guards that need no model files (unit lane).

Runs in an isolated subprocess so that ``'rapidocr' in sys.modules`` reflects
only what ``load()`` itself imported.
"""

import json
import subprocess
import sys

from snapocr.engines.config import CLS_MODEL, DET_MODEL, REC_MODEL


def test_empty_model_dir_fails_before_importing_rapidocr(tmp_path):
    code = (
        "import json, sys\n"
        "from pathlib import Path\n"
        "from snapocr.engines.config import OcrEngineConfig\n"
        "from snapocr.engines.errors import EngineLoadError\n"
        "from snapocr.engines.rapidocr_engine import RapidOcrEngine\n"
        "out = {'raised': None}\n"
        "try:\n"
        f"    RapidOcrEngine(OcrEngineConfig(model_dir=Path({str(tmp_path)!r}))).load()\n"
        "except EngineLoadError as exc:\n"
        "    out = {'raised': 'EngineLoadError', 'paths': [str(p) for p in exc.model_paths],\n"
        "           'message': str(exc)}\n"
        "out['rapidocr_imported'] = 'rapidocr' in sys.modules\n"
        "print(json.dumps(out))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-I", "-c", code],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout.strip().splitlines()[-1])

    assert out["raised"] == "EngineLoadError"
    assert out["paths"] == [str(tmp_path / DET_MODEL), str(tmp_path / CLS_MODEL), str(tmp_path / REC_MODEL)]
    assert "rapidocr==3.10.0" in out["message"]
    assert out["rapidocr_imported"] is False
