"""WI-11: partial rapidocr outputs on the real classes and the real engine (engine lane).

Pairs the fake-based unit tests in ``test_output_to_result.py``: the same four
branches are checked on objects built from the real rapidocr 3.10 output
classes, and the real path is checked by making the loaded engine's
recognition step raise ``RapidOCRError`` (which rapidocr swallows and turns
into a ``TextDetOutput``).
"""

from pathlib import Path

import numpy as np
import pytest
from rapidocr.ch_ppocr_cls import TextClsOutput
from rapidocr.ch_ppocr_det import TextDetOutput
from rapidocr.ch_ppocr_rec import TextRecOutput
from rapidocr.main import RapidOCRError
from rapidocr.utils.output import RapidOCROutput

from snapocr.engines.convert import output_to_result
from snapocr.engines.errors import EngineRuntimeError
from snapocr.engines.types import OcrResult

pytestmark = pytest.mark.engine

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
BOX = [[1.0, 2.0], [30.0, 2.0], [30.0, 12.0], [1.0, 12.0]]


def _read(path: Path) -> bytes:
    if not path.is_file():
        pytest.fail(f"missing test fixture {path}; regenerate with tests/fixtures/make_fixtures.ps1")
    return path.read_bytes()


# --- pairing: real rapidocr output classes ------------------------------------


def test_real_det_output_with_boxes_raises_with_count():
    output = TextDetOutput(boxes=np.array([BOX, BOX, BOX], dtype=np.float32), scores=[0.9, 0.8, 0.7])

    with pytest.raises(EngineRuntimeError) as info:
        output_to_result(output, 0.5)

    assert "3 text box" in str(info.value)


def test_real_empty_det_output_returns_empty_result():
    assert output_to_result(TextDetOutput(), 0.5) == OcrResult(())


def test_real_cls_output_raises_naming_type():
    with pytest.raises(EngineRuntimeError) as info:
        output_to_result(TextClsOutput(), 0.5)

    assert "TextClsOutput" in str(info.value)


def test_real_empty_rapidocr_output_returns_empty_result():
    assert output_to_result(RapidOCROutput(), 0.5) == OcrResult(())


def test_real_rec_output_raises_engine_runtime_error():
    with pytest.raises(EngineRuntimeError):
        output_to_result(TextRecOutput(txts=("abc",), scores=[0.9]), 0.5)


# --- real path: recognition step fails inside the loaded engine ---------------


def test_recognition_failure_raises_without_leaking_text(loaded_engine, monkeypatch):
    def failing_rec(img):
        raise RapidOCRError("simulated recognition failure")

    monkeypatch.setattr(loaded_engine._ocr, "recognize_txt", failing_rec)
    data = _read(FIXTURES / "mixed.png")
    expected_lines = [
        line for line in _read(FIXTURES / "mixed.txt").decode("utf-8").splitlines() if line.strip()
    ]

    with pytest.raises(EngineRuntimeError) as info:
        loaded_engine.recognize(data)

    message = str(info.value)
    assert "text box" in message
    for line in expected_lines:
        assert line not in message
        for word in line.split():
            if len(word) > 3:
                assert word not in message


def test_engine_recovers_after_failure_is_removed(loaded_engine, monkeypatch):
    data = _read(FIXTURES / "mixed.png")
    with monkeypatch.context() as m:
        m.setattr(loaded_engine._ocr, "recognize_txt", lambda img: (_ for _ in ()).throw(RapidOCRError("x")))
        with pytest.raises(EngineRuntimeError):
            loaded_engine.recognize(data)

    result = loaded_engine.recognize(data)
    assert "Hello" in "".join(block.text for block in result.blocks)
