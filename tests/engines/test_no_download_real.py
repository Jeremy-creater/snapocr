"""WI-12: load() never downloads, even for a rec model without a character dict (engine lane).

Pairs the fake-class unit tests in ``test_offline_guard.py``. A rec model
without an embedded dictionary is simulated by making the real onnxruntime
session's ``have_key`` return False. Every case runs under ``no_network``
(positive control: ``tests/test_netguard.py``), so even without the guard
nothing is fetched.

Measured on rapidocr 3.10: for the pinned PP-OCRv6 rec config,
``get_dict_key_url`` itself fails (that config has no ``dict_url``), so the
download branch is not reached. Configs that do have a ``dict_url`` (e.g.
PP-OCRv4) reach ``DownloadFile.run``; that is simulated by also making
``get_dict_key_url`` return rapidocr's own default dictionary URL.
"""

import hashlib
import shutil
from pathlib import Path

import pytest
from rapidocr.ch_ppocr_rec.main import DEFAULT_DICT_URL
from rapidocr.inference_engine.onnxruntime.main import OrtInferSession
from rapidocr.utils.download_file import DownloadFile

from snapocr.engines.config import REC_MODEL, OcrEngineConfig
from snapocr.engines.errors import EngineLoadError
from snapocr.engines.rapidocr_engine import RapidOcrEngine

pytestmark = pytest.mark.engine


def _sha256_tree(root: Path) -> dict[str, str]:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.iterdir())}


@pytest.fixture
def copied_models(real_model_paths, tmp_path):
    for src in (real_model_paths.det, real_model_paths.cls, real_model_paths.rec):
        shutil.copyfile(src, tmp_path / src.name)
    return tmp_path


def _no_embedded_dict(monkeypatch):
    monkeypatch.setattr(OrtInferSession, "have_key", lambda self, key="character": False)


def _dict_needs_download(monkeypatch):
    _no_embedded_dict(monkeypatch)
    monkeypatch.setattr(OrtInferSession, "get_dict_key_url", classmethod(lambda cls, file_info: DEFAULT_DICT_URL))


def test_rec_model_without_dict_fails_load_without_any_download(no_network, copied_models, monkeypatch):
    _dict_needs_download(monkeypatch)
    original_run = vars(DownloadFile)["run"]
    before = _sha256_tree(copied_models)
    rec = copied_models / REC_MODEL

    with pytest.raises(EngineLoadError) as info:
        RapidOcrEngine(OcrEngineConfig(model_dir=copied_models)).load()

    err = info.value
    assert err.model_paths == (rec,)
    message = str(err)
    assert str(rec) in message
    assert "character dictionary" in message
    assert "offline" in message
    assert "embedded character dictionary" in message
    assert no_network.attempts == []
    assert _sha256_tree(copied_models) == before
    assert vars(DownloadFile)["run"] is original_run


def test_pinned_v6_rec_without_dict_fails_load_naming_rec_offline(no_network, copied_models, monkeypatch):
    _no_embedded_dict(monkeypatch)
    original_run = vars(DownloadFile)["run"]
    before = _sha256_tree(copied_models)

    with pytest.raises(EngineLoadError) as info:
        RapidOcrEngine(OcrEngineConfig(model_dir=copied_models)).load()

    assert info.value.model_paths == (copied_models / REC_MODEL,)
    assert no_network.attempts == []
    assert _sha256_tree(copied_models) == before
    assert vars(DownloadFile)["run"] is original_run


def test_download_guard_restored_after_successful_and_failed_load(no_network, copied_models, monkeypatch):
    original_run = vars(DownloadFile)["run"]

    engine = RapidOcrEngine(OcrEngineConfig(model_dir=copied_models)).load()
    assert type(engine) is RapidOcrEngine
    assert vars(DownloadFile)["run"] is original_run

    _dict_needs_download(monkeypatch)
    with pytest.raises(EngineLoadError):
        RapidOcrEngine(OcrEngineConfig(model_dir=copied_models)).load()
    assert vars(DownloadFile)["run"] is original_run
    assert no_network.attempts == []
