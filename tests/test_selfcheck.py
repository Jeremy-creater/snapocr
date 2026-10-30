"""M8 WI-15: ``snapocr --self-check IMAGE REPORT`` (PRD F22-4).

Pinned here:
- ``parse_args``: ``--self-check`` takes exactly two paths (image, report); absent it is None.
- ``run_self_check(image, report, load_engine)`` writes a JSON report and returns the exit
  code: ``ok`` true and the recognized lines in ``text`` on success (exit 0); ``ok`` false
  and the error type and message in ``error`` on any failure (exit 1). The report always
  names the snapocr version and whether this is the packaged build. Missing report folders
  are created.
- The real engine path is in tests/engines/test_selfcheck_real.py (engine lane).
"""

import ast
import json
from pathlib import Path

import pytest

import snapocr
from snapocr.app import kit_module, parse_args
from snapocr.engines.errors import EngineLoadError, InvalidImageError, InvalidImageReason
from snapocr.engines.types import OcrResult, TextBlock
from snapocr.selfcheck import run_self_check

BOX = ((0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0))


class _Engine:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.seen = result, error, []

    def recognize(self, data):
        self.seen.append(data)
        if self.error:
            raise self.error
        return self.result


def _report(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_args_take_an_image_and_a_report():
    assert parse_args([]).self_check is None
    args = parse_args(["--self-check", "a.png", "out/r.json"])
    assert args.self_check == [Path("a.png"), Path("out/r.json")]
    with pytest.raises(SystemExit) as info:
        parse_args(["--self-check", "a.png"])
    assert info.value.code == 2


def test_success_writes_the_text_and_exits_0(tmp_path):
    image = tmp_path / "in.png"
    image.write_bytes(b"png bytes")
    engine = _Engine(OcrResult((TextBlock("第一行", BOX, 0.9), TextBlock("second line", BOX, 0.8))))
    report = tmp_path / "deep" / "er" / "report.json"

    code = run_self_check(image, report, lambda: engine)

    assert code == 0
    assert engine.seen == [b"png bytes"]
    assert _report(report) == {
        "ok": True,
        "version": snapocr.__version__,
        "frozen": False,
        "text": "第一行\nsecond line",
        "error": "",
    }


def test_an_image_without_text_is_still_ok(tmp_path):
    image = tmp_path / "blank.png"
    image.write_bytes(b"x")
    report = tmp_path / "r.json"
    assert run_self_check(image, report, lambda: _Engine(OcrResult(()))) == 0
    assert _report(report)["ok"] is True and _report(report)["text"] == ""


def _failing(tmp_path, image, load_engine):
    report = tmp_path / "r.json"
    code = run_self_check(image, report, load_engine)
    data = _report(report)
    assert code == 1
    assert data["ok"] is False and data["text"] == ""
    assert data["version"] == snapocr.__version__
    return data["error"]


def test_missing_image_is_reported(tmp_path):
    error = _failing(tmp_path, tmp_path / "nope.png", lambda: _Engine(OcrResult(())))
    assert error.startswith("FileNotFoundError: ") and "nope.png" in error


def test_engine_that_cannot_load_is_reported(tmp_path):
    image = tmp_path / "in.png"
    image.write_bytes(b"x")

    def load():
        raise EngineLoadError((), "models gone")

    error = _failing(tmp_path, image, load)
    assert error.startswith("EngineLoadError: ") and "models gone" in error


def test_image_the_engine_rejects_is_reported(tmp_path):
    image = tmp_path / "in.png"
    image.write_bytes(b"not a png")
    engine = _Engine(error=InvalidImageError(InvalidImageReason.NOT_PNG, "no PNG signature"))
    error = _failing(tmp_path, image, lambda: engine)
    assert error.startswith("InvalidImageError: ")


def test_any_other_crash_is_reported_too(tmp_path):
    image = tmp_path / "in.png"
    image.write_bytes(b"x")
    error = _failing(tmp_path, image, lambda: _Engine(error=RuntimeError("boom")))
    assert error == "RuntimeError: boom"


def test_a_platform_module_that_will_not_load_fails_the_check(tmp_path, monkeypatch):
    # The packaged app crashed at start while this check said ok (M9): nothing here loaded the GUI side.
    from snapocr.__main__ import main  # imported late: runpy in test_app warns if collection imported it
    from snapocr.gui.platform import launch

    def missing():
        raise ModuleNotFoundError("No module named 'snapocr.gui.platform.win'")

    monkeypatch.setattr(launch, "platform_kit", missing)
    image = tmp_path / "in.png"
    image.write_bytes(b"x")
    report = tmp_path / "r.json"

    assert main(["snapocr", "--self-check", str(image), str(report)]) == 1
    assert _report(report)["ok"] is False
    assert _report(report)["error"] == "ModuleNotFoundError: No module named 'snapocr.gui.platform.win'"


def test_the_windows_build_bundles_the_module_loaded_by_name():
    # PyInstaller cannot see importlib.import_module(name), so the spec has to name it.
    spec = ast.parse((Path(__file__).resolve().parent.parent / "packaging" / "snapocr.spec").read_text(encoding="utf-8"))
    analysis = next(n for n in ast.walk(spec) if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "Analysis")
    hidden = next(k.value for k in analysis.keywords if k.arg == "hiddenimports")
    assert kit_module("win32") in ast.literal_eval(hidden)
