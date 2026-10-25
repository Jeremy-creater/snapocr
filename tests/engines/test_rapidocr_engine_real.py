"""WI-6: the RapidOCR adapter on the real in-process models (engine lane).

Pairs the fake-based unit tests of WI-2 (convert), WI-3 (PNG check) and
WI-5 (holder) with the real path. Inputs are the committed fixtures only.
"""

import logging
import os
import struct
from pathlib import Path

import pytest

from snapocr.engines.config import OcrEngineConfig
from snapocr.engines.errors import InvalidImageError, InvalidImageReason
from snapocr.engines.image_check import check_png_bytes
from snapocr.engines.rapidocr_engine import RapidOcrEngine
from snapocr.engines.types import OcrResult, TextBlock
from support.png import set_ihdr_size

pytestmark = pytest.mark.engine

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
MIXED_PATH = FIXTURES / "mixed.png"
R = InvalidImageReason


def _fixture(name: str) -> bytes:
    path = FIXTURES / name
    if not path.is_file():
        pytest.fail(f"missing test fixture {path}; regenerate with tests/fixtures/make_fixtures.ps1")
    return path.read_bytes()


@pytest.fixture(scope="module")
def mixed() -> bytes:
    return _fixture("mixed.png")


@pytest.fixture(scope="module")
def zero_engine(real_model_paths):
    return RapidOcrEngine(OcrEngineConfig(min_score=0.0)).load()


@pytest.fixture(scope="module")
def r0(zero_engine, mixed) -> OcrResult:
    return zero_engine.recognize(mixed)


def _reject(engine, data) -> InvalidImageError:
    with pytest.raises(InvalidImageError) as info:
        engine.recognize(data)
    return info.value


# --- success / invariants ----------------------------------------------------


def test_recognize_mixed_block_invariants(loaded_engine, mixed):
    w, h = check_png_bytes(mixed)
    result = loaded_engine.recognize(mixed)

    assert type(result) is OcrResult
    assert len(result.blocks) >= 2
    for block in result.blocks:
        assert type(block) is TextBlock
        assert type(block.text) is str and block.text.strip()
        assert type(block.score) is float
        assert 0.5 <= block.score <= 1.0
        assert type(block.box) is tuple and len(block.box) == 4
        for point in block.box:
            assert type(point) is tuple and len(point) == 2
            x, y = point
            assert type(x) is float and type(y) is float
            assert 0.0 <= x <= w and 0.0 <= y <= h


def test_min_score_metamorphic_on_real_engine(loaded_engine, r0, mixed):
    r5 = loaded_engine.recognize(mixed)
    assert r5.blocks == tuple(b for b in r0.blocks if b.score >= 0.5)


def test_min_score_above_some_scores_filters_on_real_engine(r0, mixed, real_model_paths):
    s = sorted({b.score for b in r0.blocks})
    if len(s) < 2:
        pytest.fail(f"need >= 2 distinct real scores to place a threshold between them, got {s}")
    t = (s[0] + s[1]) / 2

    r_t = RapidOcrEngine(OcrEngineConfig(min_score=t)).load().recognize(mixed)

    assert r_t.blocks == tuple(b for b in r0.blocks if b.score >= t)
    assert 0 < len(r_t.blocks) < len(r0.blocks)


def test_low_confidence_block_survives_zero_threshold(zero_engine):
    result = zero_engine.recognize(_fixture("lowconf.png"))
    assert any(b.score < 0.5 for b in result.blocks), [b.score for b in result.blocks]


def test_recognize_blank_returns_empty(loaded_engine):
    assert loaded_engine.recognize(_fixture("blank.png")) == OcrResult(())


def test_bytearray_equals_bytes(loaded_engine, mixed):
    from_bytes = loaded_engine.recognize(mixed)
    assert len(from_bytes.blocks) >= 2
    assert loaded_engine.recognize(bytearray(mixed)) == from_bytes


# --- failure modes / guards --------------------------------------------------


def _cut_at_half_idat(data: bytes) -> bytes:
    pos = 8
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        kind = data[pos + 4 : pos + 8]
        if kind == b"IDAT":
            return data[: pos + 8 + length // 2]
        pos += 12 + length
    pytest.fail("fixture has no IDAT chunk")


def test_truncated_png_raises_decode_failed(loaded_engine, mixed):
    truncated = _cut_at_half_idat(mixed)
    assert check_png_bytes(truncated) == check_png_bytes(mixed)  # header still valid

    err = _reject(loaded_engine, truncated)
    assert err.reason is R.DECODE_FAILED


def _jpeg_of(data: bytes) -> bytes:
    import cv2
    import numpy as np

    ok, buf = cv2.imencode(".jpg", cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR))
    assert ok
    return buf.tobytes()


@pytest.mark.parametrize("kind", ["jpeg", "zero_width_ihdr"])
def test_non_png_rejected_by_adapter(loaded_engine, mixed, kind):
    if kind == "jpeg":
        data = _jpeg_of(mixed)
        assert data[:2] == b"\xff\xd8"
    else:
        data = set_ihdr_size(mixed, 0, check_png_bytes(mixed)[1])

    err = _reject(loaded_engine, data)
    assert err.reason is R.NOT_PNG
    if kind == "zero_width_ihdr":
        assert "invalid IHDR dimensions" in str(err)


@pytest.mark.parametrize(
    ("data", "reason"),
    [
        pytest.param(str(MIXED_PATH), R.NOT_BYTES, id="str-existing-path"),
        pytest.param("http://127.0.0.1:9/x.png", R.NOT_BYTES, id="str-url"),
        pytest.param(b"", R.EMPTY, id="empty-bytes"),
    ],
)
def test_str_and_empty_rejected_before_engine(loaded_engine, no_network, data, reason):
    assert MIXED_PATH.is_file()
    err = _reject(loaded_engine, data)
    assert err.reason is reason
    assert no_network.attempts == []


# --- privacy -----------------------------------------------------------------


def _capture_all(capfd, caplog) -> None:
    caplog.set_level(logging.DEBUG)
    caplog.set_level(logging.DEBUG, logger="snapocr")
    capfd.readouterr()


def _captured(capfd, caplog) -> str:
    out, err = capfd.readouterr()
    return "\n".join([out, err, caplog.text])


def test_recognize_does_not_leak_text(loaded_engine, mixed, capfd, caplog):
    truth = [line for line in (FIXTURES / "mixed.txt").read_text(encoding="utf-8").splitlines() if line.strip()]
    _capture_all(capfd, caplog)

    result = loaded_engine.recognize(mixed)
    captured = _captured(capfd, caplog)

    needles = truth + [b.text for b in result.blocks if len(b.text) >= 2]
    assert len(truth) == 2 and len(needles) >= 4
    leaked = [n for n in needles if n in captured]
    assert leaked == []


def test_privacy_capture_positive_control(capfd, caplog):
    _capture_all(capfd, caplog)

    logging.getLogger("snapocr.privacy_probe").debug("probe-via-logger")
    os.write(2, b"probe-via-fd2\n")
    captured = _captured(capfd, caplog)

    assert "probe-via-logger" in captured
    assert "probe-via-fd2" in captured
