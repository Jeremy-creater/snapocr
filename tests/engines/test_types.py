"""WI-1: engine-agnostic result types (TextBlock, OcrResult)."""

import dataclasses
import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from snapocr.engines.types import OcrResult, TextBlock

VALID_BOX = ((0, 0), (10, 0), (10, 5), (0, 5))


def _block(text="a", box=VALID_BOX, score=0.9):
    return TextBlock(text=text, box=box, score=score)


def test_textblock_keeps_fields_and_coerces_coords_to_float():
    b = TextBlock(text="使用Python3", box=((0, 0), (10, 0), (10, 5), (0, 5)), score=0.75)

    assert b.text == "使用Python3"
    assert b.score == 0.75
    assert type(b.score) is float
    assert b.box == ((0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0))
    assert type(b.box) is tuple
    for point in b.box:
        assert type(point) is tuple
        for c in point:
            assert type(c) is float


def test_textblock_box_is_deeply_immutable():
    b = TextBlock(text="t", box=[[0, 0], [1, 0], [1, 1], [0, 1]], score=0.5)

    assert type(b.box) is tuple
    assert all(type(p) is tuple for p in b.box)
    with pytest.raises(TypeError):
        b.box[0][0] = 9  # type: ignore[index]
    with pytest.raises(dataclasses.FrozenInstanceError):
        b.text = "x"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("kwargs", "field"),
    [
        pytest.param({"box": ((0, 0), (1, 0), (1, 1))}, "box", id="box-3-points"),
        pytest.param({"box": ((0, 0), (1, 0), (1, 1), (0, 1), (2, 2))}, "box", id="box-5-points"),
        pytest.param({"box": ((0, 0, 0), (1, 0), (1, 1), (0, 1))}, "box", id="point-3-components"),
        pytest.param({"box": ((0,), (1, 0), (1, 1), (0, 1))}, "box", id="point-1-component"),
        pytest.param({"box": ((math.inf, 0), (1, 0), (1, 1), (0, 1))}, "box", id="coord-inf"),
        pytest.param({"box": ((0, -math.inf), (1, 0), (1, 1), (0, 1))}, "box", id="coord-neg-inf"),
        pytest.param({"box": ((0, 0), (math.nan, 0), (1, 1), (0, 1))}, "box", id="coord-nan"),
        pytest.param({"box": (("1.0", 0), (1, 0), (1, 1), (0, 1))}, "box", id="coord-str"),
        pytest.param({"box": ((True, 0), (1, 0), (1, 1), (0, 1))}, "box", id="coord-bool"),
        pytest.param({"box": ((10**400, 0), (1, 0), (1, 1), (0, 1))}, "box", id="coord-int-overflow"),
        pytest.param({"box": None}, "box", id="box-none"),
        pytest.param({"box": "abcd"}, "box", id="box-str"),
        pytest.param({"box": ("ab", (1, 0), (1, 1), (0, 1))}, "box", id="point-str"),
        pytest.param({"score": -0.01}, "score", id="score-below-0"),
        pytest.param({"score": 1.01}, "score", id="score-above-1"),
        pytest.param({"score": math.nan}, "score", id="score-nan"),
        pytest.param({"score": "0.5"}, "score", id="score-str"),
        pytest.param({"score": None}, "score", id="score-none"),
        pytest.param({"text": None}, "text", id="text-none"),
        pytest.param({"text": b"x"}, "text", id="text-bytes"),
    ],
)
def test_textblock_rejects_invalid_fields(kwargs, field):
    args = {"text": "ok", "box": VALID_BOX, "score": 0.5, **kwargs}
    with pytest.raises(ValueError, match=field):
        TextBlock(**args)


def test_textblock_score_bounds_inclusive():
    assert _block(score=0.0).score == 0.0
    assert _block(score=1.0).score == 1.0
    with pytest.raises(ValueError, match="score"):
        _block(score=math.nextafter(0.0, -1))
    with pytest.raises(ValueError, match="score"):
        _block(score=math.nextafter(1.0, 2))


_any_coord = st.one_of(
    st.floats(allow_nan=True, allow_infinity=True),
    st.integers(),
    st.text(max_size=3),
)
_any_point = st.lists(_any_coord, min_size=1, max_size=3)
_any_box = st.one_of(
    st.lists(_any_point, min_size=0, max_size=6),
    st.lists(_any_point.map(tuple), min_size=0, max_size=6).map(tuple),
)


@given(
    text=st.one_of(st.text(), st.none(), st.integers(), st.binary()),
    box=_any_box,
    score=st.one_of(st.floats(), st.integers(-2, 2), st.text(max_size=3)),
)
def test_textblock_validation_is_total(text, box, score):
    try:
        b = TextBlock(text=text, box=box, score=score)
    except ValueError:
        return
    # Construction succeeded: every constraint must hold.
    assert type(b.text) is str
    assert type(b.box) is tuple and len(b.box) == 4
    for point in b.box:
        assert type(point) is tuple and len(point) == 2
        for c in point:
            assert type(c) is float and math.isfinite(c)
    assert type(b.score) is float
    assert 0.0 <= b.score <= 1.0


_valid_coord = st.one_of(
    st.floats(allow_nan=False, allow_infinity=False),
    st.integers(-(10**6), 10**6),
)
_valid_point = st.tuples(_valid_coord, _valid_coord)
_valid_block = st.builds(
    TextBlock,
    text=st.text(),
    box=st.tuples(_valid_point, _valid_point, _valid_point, _valid_point),
    score=st.floats(min_value=0.0, max_value=1.0),
)


@given(_valid_block)
def test_textblock_reconstruct_roundtrip(b):
    rebuilt = TextBlock(b.text, b.box, b.score)
    assert rebuilt == b
    assert hash(rebuilt) == hash(b)
    assert len({rebuilt, b}) == 1


def test_ocr_result_is_empty_and_equality():
    b1 = _block(text="one")
    b2 = _block(text="two")

    empty = OcrResult(())
    single = OcrResult((b1,))
    from_list = OcrResult([b1, b2])

    assert empty.is_empty is True
    assert single.is_empty is False
    assert from_list.is_empty is False
    assert type(from_list.blocks) is tuple
    assert from_list == OcrResult((b1, b2))
    assert OcrResult((b1, b2)) != OcrResult((b2, b1))
    assert empty == OcrResult([])
    assert hash(from_list) == hash(OcrResult((b1, b2)))
    with pytest.raises(dataclasses.FrozenInstanceError):
        empty.blocks = (b1,)  # type: ignore[misc]


@pytest.mark.parametrize(
    "blocks",
    [
        pytest.param(("text",), id="str-element"),
        pytest.param((None,), id="none-element"),
        pytest.param(None, id="blocks-none"),
        pytest.param(42, id="blocks-int"),
    ],
)
def test_ocr_result_rejects_non_textblock(blocks):
    with pytest.raises(ValueError, match="blocks"):
        OcrResult(blocks)
