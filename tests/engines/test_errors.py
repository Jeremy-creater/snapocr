"""WI-1: engine-agnostic exception hierarchy."""

from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from snapocr.engines.errors import (
    EngineLoadError,
    EngineRuntimeError,
    InvalidImageError,
    InvalidImageReason,
    OcrError,
)

EXPECTED_REASONS = {"NOT_BYTES", "EMPTY", "NOT_PNG", "TRUNCATED", "DECODE_FAILED"}


def test_reason_members_are_exactly_the_planned_five():
    assert {r.name for r in InvalidImageReason} == EXPECTED_REASONS


@pytest.mark.parametrize("reason", list(InvalidImageReason), ids=lambda r: r.name)
def test_error_hierarchy_and_messages(reason):
    e = InvalidImageError(reason=reason, detail="got 7 bytes")

    assert isinstance(e, OcrError)
    assert isinstance(e, Exception)
    assert e.reason is reason
    assert e.detail == "got 7 bytes"
    msg = str(e)
    assert reason.name in msg
    assert "got 7 bytes" in msg


def test_invalid_image_messages_distinct_across_reasons():
    messages = {str(InvalidImageError(reason=r, detail="same")) for r in InvalidImageReason}
    assert len(messages) == len(InvalidImageReason)


def test_invalid_image_message_without_detail_still_names_reason():
    e = InvalidImageError(reason=InvalidImageReason.EMPTY)
    assert "EMPTY" in str(e)
    assert e.detail == ""


def test_engine_runtime_error_is_ocr_error_with_message():
    e = EngineRuntimeError("boxes/txts length mismatch")
    assert isinstance(e, OcrError)
    assert not isinstance(e, (InvalidImageError, EngineLoadError))
    assert "boxes/txts length mismatch" in str(e)


_name_chars = st.sampled_from(list("abcXYZ_-") + list("模型路径识别"))
_filename = st.text(alphabet=_name_chars, min_size=1, max_size=12).map(lambda s: s + ".onnx")
_hint = st.text(min_size=1, max_size=40).filter(lambda s: s.strip() != "")


@given(names=st.lists(_filename, min_size=1, max_size=3), hint=_hint)
def test_engine_load_error_message_contains_every_path_and_hint(names, hint):
    paths = [Path("D:/LLM/models") / n for n in names]

    e = EngineLoadError(model_paths=paths, hint=hint)

    assert isinstance(e, OcrError)
    assert e.model_paths == tuple(paths)
    assert e.hint == hint
    msg = str(e)
    for p in paths:
        assert str(p) in msg
    assert hint in msg
