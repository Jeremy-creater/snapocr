"""``snapocr --self-check IMAGE REPORT`` (PRD F22-4). No Qt.

Recognizes one image with the bundled models and writes a JSON report, so the release
workflow can check that the packaged exe (which has no console) really works offline.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path

import snapocr
from snapocr.engines.types import OcrEngine


def run_self_check(image: Path, report: Path, load_engine: Callable[[], OcrEngine]) -> int:
    """Write the report; exit code 0 when the image was recognized, 1 on any failure."""
    result = {
        "ok": False,
        "version": snapocr.__version__,
        "frozen": bool(getattr(sys, "frozen", False)),
        "text": "",
        "error": "",
    }
    try:
        data = Path(image).read_bytes()
        blocks = load_engine().recognize(data).blocks
        result.update(ok=True, text="\n".join(block.text for block in blocks))
    except Exception as exc:  # every failure belongs in the report, not in a traceback nobody sees
        result["error"] = f"{type(exc).__name__}: {exc}"
    report = Path(report)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if result["ok"] else 1
