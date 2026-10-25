"""WI-13 (C1/M1): recognize() maps engine exceptions onto the OcrError hierarchy (unit lane).

The RapidOCR instance is replaced by a plain fake callable (the boundary to the
OCR runtime), so no model is loaded. The real path is paired in
``test_recognize_exception_real.py`` (engine lane).

Law: the mapping is total. Every ``Exception`` raised by the engine call ends
up as an ``OcrError``: an ``OcrError`` passes through unchanged (``is``), any
other ``Exception`` becomes ``EngineRuntimeError("OCR engine failed: <Type>")``
with the original as ``__cause__`` and none of its text in the message.
``BaseException`` outside ``Exception`` is never caught.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from snapocr.engines.config import OcrEngineConfig
from snapocr.engines.errors import (
    EngineLoadError,
    EngineRuntimeError,
    InvalidImageError,
    InvalidImageReason,
    OcrError,
)
from snapocr.engines.rapidocr_engine import RapidOcrEngine
from support.png import make_png

PNG = make_png(8, 8)
SECRET = "Hello secret OCR text 你好"


class CustomEngineFailure(Exception):
    """A third-party exception type the adapter cannot know about."""


class AllocationFailure(MemoryError):
    """An out-of-memory subclass (named so runner logs never show a real OOM)."""


class Raiser:
    """Fake OCR callable: raises the given exception and records each call."""

    def __init__(self, exc: BaseException) -> None:
        self.exc = exc
        self.calls = 0

    def __call__(self, image):
        self.calls += 1
        raise self.exc


def _engine_raising(exc: BaseException) -> tuple[RapidOcrEngine, Raiser]:
    engine = RapidOcrEngine(OcrEngineConfig())
    fake = Raiser(exc)
    engine._ocr = fake
    return engine, fake


def test_value_error_is_wrapped_with_type_name_only():
    original = ValueError(SECRET)
    engine, fake = _engine_raising(original)

    with pytest.raises(EngineRuntimeError) as info:
        engine.recognize(PNG)

    assert fake.calls == 1
    assert str(info.value) == "OCR engine failed: ValueError"
    assert info.value.__cause__ is original
    assert "Hello" not in str(info.value)
    assert "你好" not in str(info.value)


def test_engine_runtime_error_passes_through_unchanged():
    original = EngineRuntimeError("already mapped")
    engine, _ = _engine_raising(original)

    with pytest.raises(EngineRuntimeError) as info:
        engine.recognize(PNG)

    assert info.value is original
    assert str(info.value) == "already mapped"


def test_other_ocr_error_subclass_passes_through_unchanged():
    original = InvalidImageError(InvalidImageReason.DECODE_FAILED, "from engine")
    engine, _ = _engine_raising(original)

    with pytest.raises(InvalidImageError) as info:
        engine.recognize(PNG)

    assert info.value is original


def test_keyboard_interrupt_is_not_caught():
    original = KeyboardInterrupt()
    engine, _ = _engine_raising(original)

    with pytest.raises(KeyboardInterrupt) as info:
        engine.recognize(PNG)

    assert info.value is original


def test_invalid_image_is_rejected_before_engine_is_called():
    engine, fake = _engine_raising(ValueError(SECRET))

    with pytest.raises(InvalidImageError):
        engine.recognize(b"not a png")

    assert fake.calls == 0


NON_OCR_TYPES = [
    RuntimeError,
    ValueError,
    TypeError,
    IndexError,
    KeyError,
    AttributeError,
    AllocationFailure,
    OSError,
    ZeroDivisionError,
    AssertionError,
    NotImplementedError,
    UnicodeDecodeError,
    CustomEngineFailure,
]


def _build(exc_type: type[Exception], text: str) -> Exception:
    if exc_type is UnicodeDecodeError:
        return UnicodeDecodeError("utf-8", text.encode("utf-8"), 0, 1, text)
    return exc_type(text)


@given(exc_type=st.sampled_from(NON_OCR_TYPES), text=st.text(min_size=1, max_size=40))
def test_property_any_non_ocr_exception_maps_to_engine_runtime_error(exc_type, text):
    original = _build(exc_type, text)
    engine, _ = _engine_raising(original)

    with pytest.raises(OcrError) as info:
        engine.recognize(PNG)

    err = info.value
    assert type(err) is EngineRuntimeError
    assert str(err) == f"OCR engine failed: {exc_type.__name__}"
    assert err.__cause__ is original


@given(
    ocr_error=st.sampled_from(
        [
            EngineRuntimeError("runtime"),
            InvalidImageError(InvalidImageReason.TRUNCATED),
            EngineLoadError(("m.onnx",), "hint"),
            OcrError("base"),
        ]
    )
)
def test_property_ocr_errors_pass_through_by_identity(ocr_error):
    engine, _ = _engine_raising(ocr_error)

    with pytest.raises(OcrError) as info:
        engine.recognize(PNG)

    assert info.value is ocr_error
