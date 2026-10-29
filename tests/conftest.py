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
from hypothesis import settings

from snapocr.engines.config import OcrEngineConfig, resolve_model_paths
from snapocr.engines.rapidocr_engine import RapidOcrEngine
from support.engine_require import require_model_files
from support.fake_openai_server import FakeOpenAIServer
from support.netguard import LoopbackGuard, NetGuard
from support.ollama_require import require_ollama as _require_ollama

pytest_plugins = ["pytester", "support.qt_lane", "support.platform_lanes"]

FIXTURES = Path(__file__).parent / "fixtures"

# Hypothesis example budget (CLAUDE.md, FIX-2). Every lane runs "unit";
# ``--hypothesis-profile=thorough`` overrides it for a manual run.
settings.register_profile("unit", max_examples=50)
settings.register_profile("thorough", max_examples=200)
settings.load_profile("unit")


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


@pytest.fixture(scope="session")
def require_ollama():
    """Integration lane: FAIL (never skip) unless Ollama runs with hy-mt2:7b imported."""
    _require_ollama()
