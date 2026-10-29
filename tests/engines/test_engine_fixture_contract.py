"""WI-7: the engine-lane model precondition FAILS, it never skips (unit lane)."""

from pathlib import Path

import pytest

from snapocr.engines.config import ModelPaths
from support.engine_require import require_model_files

TESTS_DIR = Path(__file__).resolve().parent.parent
FIX_CMD = "-m pip install --force-reinstall rapidocr==3.10.0"  # PRD F21-4


def _empty_paths(root: Path) -> ModelPaths:
    return ModelPaths(det=root / "det.onnx", cls=root / "cls.onnx", rec=root / "rec.onnx")


def test_require_model_files_fails_not_skips(tmp_path):
    paths = _empty_paths(tmp_path)

    with pytest.raises(BaseException) as info:  # Failed / Skipped derive from BaseException
        require_model_files(paths)

    assert isinstance(info.value, pytest.fail.Exception)
    assert not isinstance(info.value, pytest.skip.Exception)
    message = str(info.value)
    for path in (paths.det, paths.cls, paths.rec):
        assert str(path) in message
    assert FIX_CMD in message


def test_engine_session_fixture_reports_failure_via_pytester(pytester, tmp_path):
    empty = tmp_path / "no_models"
    empty.mkdir()
    pytester.makeconftest(
        f"""
import sys
sys.path.insert(0, {str(TESTS_DIR)!r})

import pytest
from pathlib import Path

from snapocr.engines.config import ModelPaths
from support.engine_require import require_model_files

EMPTY = Path({str(empty)!r})


@pytest.fixture(scope="session")
def real_model_paths():
    return require_model_files(
        ModelPaths(det=EMPTY / "det.onnx", cls=EMPTY / "cls.onnx", rec=EMPTY / "rec.onnx")
    )
"""
    )
    pytester.makepyfile(
        """
def test_uses_models(real_model_paths):
    assert real_model_paths is not None
"""
    )

    result = pytester.runpytest()

    assert result.ret != 0
    result.assert_outcomes(errors=1, passed=0, skipped=0, failed=0)
    assert FIX_CMD in result.stdout.str()
