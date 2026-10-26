"""Shared test configuration.

With pytest's default (prepend) import mode and no ``__init__.py`` under
``tests/``, this conftest puts ``tests/`` on ``sys.path``, which makes the
``support`` helpers importable as ``from support.png import ...``.

Engine-lane fixtures (``real_model_paths``, ``loaded_engine``) FAIL when the
model files are missing; they never skip. Importing the adapter module here is
cheap: rapidocr / onnxruntime / cv2 / numpy load only inside ``load()``.
"""

from pathlib import Path

import pytest

from snapocr.engines.config import OcrEngineConfig, resolve_model_paths
from snapocr.engines.rapidocr_engine import RapidOcrEngine
from support.engine_require import require_model_files
from support.fake_openai_server import FakeOpenAIServer
from support.netguard import LoopbackGuard, NetGuard

pytest_plugins = ["pytester"]

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def real_model_paths():
    try:
        paths = resolve_model_paths(OcrEngineConfig())
    except Exception as exc:  # e.g. rapidocr not installed
        pytest.fail(f"cannot locate RapidOCR models: {exc}", pytrace=False)
    return require_model_files(paths)


@pytest.fixture(scope="session")
def loaded_engine(real_model_paths):
    """A loaded RapidOcrEngine with the default config (min_score=0.5)."""
    return RapidOcrEngine(OcrEngineConfig()).load()


@pytest.fixture
def no_network(monkeypatch):
    return NetGuard().install(monkeypatch)


# --- F4 translator fixtures ------------------------------------------------------


@pytest.fixture(scope="module")
def loopback_guard():
    """Module-wide: only 127.0.0.1 may be reached; teardown fails on any other attempt."""
    with pytest.MonkeyPatch.context() as mp:
        guard = LoopbackGuard().install(mp)
        yield guard
    assert guard.blocked == [], f"non-loopback network attempts: {guard.blocked!r}"


@pytest.fixture(scope="module")
def fake_server():
    """In-process fake Ollama on 127.0.0.1; call ``reset()`` at the start of each test/example."""
    with FakeOpenAIServer() as fake:
        yield fake
