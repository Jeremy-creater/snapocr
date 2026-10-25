"""WI-11: output_to_result turns any RapidOCR output shape into OcrResult or EngineRuntimeError.

rapidocr 3.10 returns a partial output type when det / cls / rec fails
(``TextDetOutput``, ``TextClsOutput``, ``TextRecOutput``, empty ``RapidOCROutput``).
Unit lane: the shapes are imitated with plain fakes; the engine-lane pairing in
``test_recognition_failure_real.py`` uses the real rapidocr classes.

Law: for outputs that carry ``txts``, ``output_to_result(o, t)`` is equivalent
to ``to_result(o.boxes, o.txts, o.scores, t)`` (same result, or the same
EngineRuntimeError message) — S4 property below.
"""

from dataclasses import dataclass, field

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from snapocr.engines.convert import output_to_result, to_result
from snapocr.engines.errors import EngineRuntimeError
from snapocr.engines.types import OcrResult, TextBlock

BOX_A = [[1.0, 2.0], [30.0, 2.0], [30.0, 12.0], [1.0, 12.0]]
BOX_B = [[1.0, 20.0], [40.0, 20.0], [40.0, 32.0], [1.0, 32.0]]
SECRET_TEXT = "secret-text-must-not-leak"


# --- fakes mimicking the four rapidocr 3.10 output shapes --------------------


@dataclass
class FakeFullOutput:  # RapidOCROutput: boxes + txts + scores
    boxes: object = None
    txts: object = None
    scores: object = None


@dataclass
class FakeDetOutput:  # TextDetOutput: boxes + scores, no txts attribute
    boxes: object = None
    scores: object = None


@dataclass
class FakeClsOutput:  # TextClsOutput: neither txts nor boxes
    img_list: object = None
    cls_res: object = None


@dataclass
class FakeRecOutput:  # TextRecOutput: txts + scores, no boxes attribute
    txts: object = None
    scores: list = field(default_factory=lambda: [1.0])


# --- branch 1: outputs with txts go through to_result ------------------------


def test_full_output_converts_like_to_result():
    output = FakeFullOutput(
        boxes=np.array([BOX_A, BOX_B], dtype=np.float32),
        txts=("Hello", "世界"),
        scores=np.array([0.9, 0.3], dtype=np.float32),
    )

    result = output_to_result(output, 0.5)

    assert result == OcrResult(
        (TextBlock(text="Hello", box=tuple(tuple(p) for p in BOX_A), score=float(np.float32(0.9))),)
    )


def test_empty_full_output_returns_empty_result():
    assert output_to_result(FakeFullOutput(), 0.5) == OcrResult(())


def test_rec_only_output_raises_engine_runtime_error_not_attribute_error():
    output = FakeRecOutput(txts=(SECRET_TEXT,), scores=[0.99])

    with pytest.raises(EngineRuntimeError) as info:
        output_to_result(output, 0.5)

    assert "boxes is None" in str(info.value)
    assert SECRET_TEXT not in str(info.value)


# --- branch 2: no txts, no boxes -> empty ------------------------------------


@pytest.mark.parametrize(
    "boxes",
    [None, [], np.zeros((0, 4, 2), dtype=np.float32)],
    ids=["none", "empty-list", "empty-array"],
)
def test_det_output_without_boxes_returns_empty_result(boxes):
    assert output_to_result(FakeDetOutput(boxes=boxes), 0.5) == OcrResult(())


# --- branch 3: boxes detected but no recognition -> error with count ---------


@pytest.mark.parametrize("n", [1, 2, 7])
def test_det_output_with_boxes_raises_with_box_count(n):
    boxes = np.array([BOX_A] * n, dtype=np.float32)
    output = FakeDetOutput(boxes=boxes, scores=[0.9] * n)

    with pytest.raises(EngineRuntimeError) as info:
        output_to_result(output, 0.5)

    message = str(info.value)
    assert f"{n} text box" in message
    assert "recogni" in message


def test_det_output_with_list_boxes_raises_with_box_count():
    with pytest.raises(EngineRuntimeError) as info:
        output_to_result(FakeDetOutput(boxes=[BOX_A, BOX_B]), 0.5)

    assert "2 text box" in str(info.value)


def test_det_output_with_unsized_boxes_raises_engine_runtime_error():
    with pytest.raises(EngineRuntimeError) as info:
        output_to_result(FakeDetOutput(boxes=object()), 0.5)

    assert "boxes" in str(info.value)


# --- branch 4: neither txts nor boxes -> error naming the type ---------------


@pytest.mark.parametrize("output", [FakeClsOutput(), FakeClsOutput(img_list=[1], cls_res=[("0", 0.9)]), object()])
def test_output_without_txts_or_boxes_raises_naming_type(output):
    with pytest.raises(EngineRuntimeError) as info:
        output_to_result(output, 0.5)

    assert type(output).__name__ in str(info.value)


# --- property (S4): the detected-but-unrecognized error states the count -----


@given(st.integers(min_value=1, max_value=50))
def test_det_failure_message_states_count_for_any_n(n):
    boxes = np.array([BOX_A] * n, dtype=np.float32)

    with pytest.raises(EngineRuntimeError) as info:
        output_to_result(FakeDetOutput(boxes=boxes), 0.0)

    assert f"{n} text box" in str(info.value)


# --- law (S4): equivalence with to_result when txts is present ---------------

_coord = st.floats(-1e4, 1e4)
_box = st.lists(st.tuples(_coord, _coord), min_size=4, max_size=4).map(lambda b: [list(p) for p in b])
_text = st.one_of(st.text(), st.text(alphabet=" \t\n", max_size=3))


@st.composite
def full_output(draw):
    n = draw(st.integers(0, 8))
    boxes = draw(st.lists(_box, min_size=n, max_size=n))
    txts = tuple(draw(st.lists(_text, min_size=n, max_size=n)))
    scores = draw(st.lists(st.floats(0, 1), min_size=n, max_size=n))
    if draw(st.booleans()) and n:  # occasionally malformed: length mismatch
        scores = scores[:-1]
    if draw(st.booleans()):
        boxes = np.array(boxes, dtype=np.float32).reshape(len(boxes), 4, 2)
        scores = np.array(scores, dtype=np.float32)
    if n == 0 and draw(st.booleans()):
        boxes, txts, scores = None, None, None
    return FakeFullOutput(boxes=boxes, txts=txts, scores=scores)


def _outcome(fn):
    try:
        return ("ok", fn())
    except EngineRuntimeError as exc:
        return ("error", str(exc))


@given(full_output(), st.floats(0, 1))
def test_equivalent_to_to_result_when_txts_present(output, t):
    expected = _outcome(lambda: to_result(output.boxes, output.txts, output.scores, t))

    assert _outcome(lambda: output_to_result(output, t)) == expected
