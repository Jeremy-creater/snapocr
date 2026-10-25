"""WI-4: engine config, model path resolution and local model-file checks."""

import importlib.metadata
import importlib.util
import json
import math
import subprocess
import sys
from itertools import product
from pathlib import Path

import pytest

from snapocr.engines.config import (
    ModelPaths,
    OcrEngineConfig,
    check_model_files,
    resolve_model_paths,
)
from snapocr.engines.errors import EngineLoadError

DET = "PP-OCRv6_det_small.onnx"
CLS = "ch_ppocr_mobile_v2.0_cls_mobile.onnx"
REC = "PP-OCRv6_rec_small.onnx"
NAMES = (DET, CLS, REC)

SRC_DIR = Path(__file__).resolve().parents[2] / "src"


# --- OcrEngineConfig -------------------------------------------------------


def test_config_defaults():
    cfg = OcrEngineConfig()
    assert cfg.min_score == 0.5
    assert cfg.model_dir is None


@pytest.mark.parametrize("value", [0, 0.0, 1, 1.0, 0.5])
def test_config_accepts_closed_unit_interval(value):
    assert OcrEngineConfig(min_score=value).min_score == value


@pytest.mark.parametrize(
    "value",
    [-0.1, 1.1, math.nan, math.inf, -math.inf],
    ids=["neg", "above_one", "nan", "inf", "neg_inf"],
)
def test_config_rejects_out_of_range_min_score(value):
    with pytest.raises(ValueError, match="min_score"):
        OcrEngineConfig(min_score=value)


# --- resolve + check with explicit model_dir --------------------------------


def _make_ok(directory: Path) -> None:
    for name in NAMES:
        (directory / name).write_bytes(b"x")


def test_resolve_and_check_with_explicit_dir(tmp_path):
    _make_ok(tmp_path)

    paths = resolve_model_paths(OcrEngineConfig(model_dir=tmp_path))

    assert paths == ModelPaths(det=tmp_path / DET, cls=tmp_path / CLS, rec=tmp_path / REC)
    assert all(p.is_absolute() for p in (paths.det, paths.cls, paths.rec))
    assert check_model_files(paths) is None


STATES = ("ok", "missing", "dir", "empty")


def _materialize(path: Path, state: str) -> None:
    if state == "ok":
        path.write_bytes(b"x")
    elif state == "dir":
        path.mkdir()
    elif state == "empty":
        path.write_bytes(b"")
    # "missing": create nothing


@pytest.mark.parametrize(
    "states", list(product(STATES, repeat=3)), ids=lambda s: "-".join(s)
)
def test_check_reports_exactly_the_bad_set(tmp_path, states):
    for name, state in zip(NAMES, states):
        _materialize(tmp_path / name, state)
    paths = resolve_model_paths(OcrEngineConfig(model_dir=tmp_path))
    ordered = (paths.det, paths.cls, paths.rec)
    expected_bad = tuple(p for p, s in zip(ordered, states) if s != "ok")

    if not expected_bad:
        assert check_model_files(paths) is None
        return

    with pytest.raises(EngineLoadError) as excinfo:
        check_model_files(paths)
    err = excinfo.value
    assert err.model_paths == expected_bad
    msg = str(err)
    assert "--reinstall rapidocr==3.10.0" in msg
    assert "model_dir" in msg
    for p in expected_bad:
        assert str(p) in msg


# --- default model_dir: installed rapidocr, located without importing it ----


def test_default_model_dir_is_installed_rapidocr_models_without_import():
    code = (
        "import json, sys\n"
        "from snapocr.engines.config import OcrEngineConfig, resolve_model_paths\n"
        "p = resolve_model_paths(OcrEngineConfig())\n"
        "print(json.dumps({'det': str(p.det), 'cls': str(p.cls), 'rec': str(p.rec),\n"
        "    'imported': 'rapidocr' in sys.modules}))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-I", "-c", code], capture_output=True, text=True, timeout=60
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout.strip())

    assert out["imported"] is False
    expected_dir = Path(
        importlib.metadata.distribution("rapidocr").locate_file("rapidocr/models")
    ).resolve()
    for key, name in (("det", DET), ("cls", CLS), ("rec", REC)):
        p = Path(out[key])
        assert p.name == name
        assert p.parent.resolve() == expected_dir


def test_default_model_dir_in_process_matches_installed_distribution():
    # In-process twin of the subprocess case, so coverage sees the found-path branch.
    paths = resolve_model_paths(OcrEngineConfig())

    expected_dir = Path(
        importlib.metadata.distribution("rapidocr").locate_file("rapidocr/models")
    ).resolve()
    assert paths == ModelPaths(
        det=paths.det.parent / DET, cls=paths.det.parent / CLS, rec=paths.det.parent / REC
    )
    assert paths.det.parent.resolve() == expected_dir
    assert paths.det.is_absolute()


def test_rapidocr_not_installed_gives_install_hint():
    # -S skips site-packages, giving a real "rapidocr is not installed" interpreter.
    code = (
        "import json, sys\n"
        f"sys.path.insert(0, {str(SRC_DIR)!r})\n"
        "from snapocr.engines.config import OcrEngineConfig, resolve_model_paths\n"
        "from snapocr.engines.errors import EngineLoadError\n"
        "try:\n"
        "    resolve_model_paths(OcrEngineConfig())\n"
        "except EngineLoadError as e:\n"
        "    print(json.dumps({'raised': True, 'msg': str(e)}))\n"
        "else:\n"
        "    print(json.dumps({'raised': False, 'msg': ''}))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-I", "-S", "-c", code], capture_output=True, text=True, timeout=60
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout.strip())

    assert out["raised"] is True
    assert "uv pip install" in out["msg"]
    assert "rapidocr==3.10.0" in out["msg"]


def test_find_spec_none_in_process_gives_install_hint(monkeypatch):
    # In-process twin of the -S subprocess case, so coverage sees the branch.
    real_find_spec = importlib.util.find_spec

    def fake_find_spec(name, *args, **kwargs):
        if name == "rapidocr":
            return None
        return real_find_spec(name, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)

    with pytest.raises(EngineLoadError) as excinfo:
        resolve_model_paths(OcrEngineConfig())
    msg = str(excinfo.value)
    assert "uv pip install" in msg
    assert "rapidocr==3.10.0" in msg
    assert "model_dir" in msg


def test_config_module_imports_no_heavy_deps():
    heavy = ["rapidocr", "onnxruntime", "numpy", "cv2"]
    code = (
        "import json, sys\n"
        "import snapocr.engines.config\n"
        f"heavy = {heavy!r}\n"
        "print(json.dumps([m for m in heavy if m in sys.modules]))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-I", "-c", code], capture_output=True, text=True, timeout=60
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout.strip()) == []
