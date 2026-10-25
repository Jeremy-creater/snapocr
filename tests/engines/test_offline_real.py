"""WI-7: offline guarantee and real model-failure paths (engine lane).

Every case here runs under ``no_network``; its positive control is
``tests/test_netguard.py``. Corruption happens only on copies in ``tmp_path``;
the installed models are never written.
"""

import hashlib
import shutil
from pathlib import Path

import pytest

from snapocr.engines.config import CLS_MODEL, DET_MODEL, REC_MODEL, OcrEngineConfig
from snapocr.engines.errors import EngineLoadError
from snapocr.engines.holder import EngineHolder
from snapocr.engines.rapidocr_engine import RapidOcrEngine
from snapocr.engines.types import OcrResult

pytestmark = pytest.mark.engine

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
FIX_CMD = "--reinstall rapidocr==3.10.0"


def _fixture(name: str) -> bytes:
    path = FIXTURES / name
    if not path.is_file():
        pytest.fail(f"missing test fixture {path}; regenerate with tests/fixtures/make_fixtures.ps1")
    return path.read_bytes()


def _sha256_tree(root: Path) -> dict[str, str]:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.iterdir())}


def test_load_and_recognize_offline_without_state_leak(no_network, real_model_paths):
    blank, mixed = _fixture("blank.png"), _fixture("mixed.png")

    engine = RapidOcrEngine(OcrEngineConfig()).load()
    results = [engine.recognize(img) for img in (blank, mixed, blank, mixed, mixed)]

    assert results[0] == OcrResult(())
    assert results[2] == OcrResult(())
    assert len(results[1].blocks) >= 2
    assert results[1] == results[3] == results[4]
    assert no_network.attempts == []


def _truncate_half(path: Path) -> None:
    data = path.read_bytes()
    path.write_bytes(data[: len(data) // 2])


def _garbage(path: Path) -> None:
    path.write_bytes(b"garbage" * 1024)


CORRUPTIONS = {
    "det": (DET_MODEL, _garbage),
    "cls": (CLS_MODEL, _garbage),
    "rec": (REC_MODEL, _garbage),
    "rec_truncated": (REC_MODEL, _truncate_half),
}


@pytest.mark.parametrize("which", list(CORRUPTIONS))
def test_corrupt_model_raises_load_error_offline(no_network, real_model_paths, tmp_path, which):
    for src in (real_model_paths.det, real_model_paths.cls, real_model_paths.rec):
        shutil.copyfile(src, tmp_path / src.name)
    name, corrupt = CORRUPTIONS[which]
    target = tmp_path / name
    corrupt(target)
    before = _sha256_tree(tmp_path)

    with pytest.raises(EngineLoadError) as info:
        RapidOcrEngine(OcrEngineConfig(model_dir=tmp_path)).load()

    err = info.value
    assert err.model_paths == (target,)
    assert err.__cause__ is not None
    message = str(err)
    assert str(target) in message
    assert FIX_CMD in message
    assert no_network.attempts == []
    assert _sha256_tree(tmp_path) == before  # nothing re-downloaded or rewritten


def test_holder_with_real_engine_loads_once_and_reuses(no_network, real_model_paths):
    mixed = _fixture("mixed.png")
    built = []

    def factory():
        engine = RapidOcrEngine(OcrEngineConfig()).load()
        built.append(engine)
        return engine

    holder = EngineHolder(factory)

    first = holder.get()
    r1 = first.recognize(mixed)
    second = holder.get()
    r2 = second.recognize(mixed)

    assert second is first
    assert built == [first]
    assert type(first) is RapidOcrEngine
    assert len(r1.blocks) >= 2
    assert r2 == r1
    assert no_network.attempts == []
