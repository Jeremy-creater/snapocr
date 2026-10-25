"""WI-13 (M1, T2): exception mapping and CPU-only sessions on the loaded engine (engine lane).

Pairs the fake-callable unit tests in ``test_recognize_exception_mapping.py``.
rapidocr 3.10 only catches its own ``RapidOCRError`` around the recognition
step, so any other exception raised by ``recognize_txt`` reaches snapocr.

The provider check reads rapidocr 3.10.x private attributes
(``text_det/text_cls/text_rec.session.session``; version pinned in
pyproject). It proves the sessions run on CPU only, i.e. never on a remote
execution provider such as ``AzureExecutionProvider``.
"""

from pathlib import Path

import pytest

from snapocr.engines.errors import EngineRuntimeError

pytestmark = pytest.mark.engine

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
SECRET = "simulated onnxruntime failure near Hello World"


def _read(path: Path) -> bytes:
    if not path.is_file():
        pytest.fail(f"missing test fixture {path}; regenerate with tests/fixtures/make_fixtures.ps1")
    return path.read_bytes()


def test_runtime_error_in_recognition_is_wrapped_without_text(loaded_engine, monkeypatch):
    original = RuntimeError(SECRET)

    def failing_rec(img):
        raise original

    monkeypatch.setattr(loaded_engine._ocr, "recognize_txt", failing_rec)

    with pytest.raises(EngineRuntimeError) as info:
        loaded_engine.recognize(_read(FIXTURES / "mixed.png"))

    assert info.value.__cause__ is original
    assert str(info.value) == "OCR engine failed: RuntimeError"
    assert "Hello" not in str(info.value)


def test_keyboard_interrupt_in_recognition_propagates_unchanged(loaded_engine, monkeypatch):
    original = KeyboardInterrupt()

    def interrupted_rec(img):
        raise original

    monkeypatch.setattr(loaded_engine._ocr, "recognize_txt", interrupted_rec)

    with pytest.raises(KeyboardInterrupt) as info:
        loaded_engine.recognize(_read(FIXTURES / "mixed.png"))

    assert info.value is original


def test_engine_recovers_after_wrapped_runtime_error(loaded_engine, monkeypatch):
    data = _read(FIXTURES / "mixed.png")
    with monkeypatch.context() as m:
        m.setattr(loaded_engine._ocr, "recognize_txt", lambda img: (_ for _ in ()).throw(RuntimeError("x")))
        with pytest.raises(EngineRuntimeError):
            loaded_engine.recognize(data)

    result = loaded_engine.recognize(data)
    assert "Hello" in "".join(block.text for block in result.blocks)


@pytest.mark.parametrize("stage", ["text_det", "text_cls", "text_rec"])
def test_loaded_sessions_use_cpu_provider_only(loaded_engine, stage):
    ort_session = getattr(loaded_engine._ocr, stage).session.session

    assert ort_session.get_providers() == ["CPUExecutionProvider"]
