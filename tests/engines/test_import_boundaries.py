"""Import isolation: engine-agnostic modules must not pull heavy runtime deps."""

import json
import subprocess
import sys

HEAVY = ["rapidocr", "onnxruntime", "numpy", "cv2"]


def test_types_and_errors_import_no_heavy_deps():
    code = (
        "import json, sys\n"
        "import snapocr.engines.types, snapocr.engines.errors\n"
        f"heavy = {HEAVY!r}\n"
        "print(json.dumps([m for m in heavy if m in sys.modules]))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-I", "-c", code],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout.strip()) == []
