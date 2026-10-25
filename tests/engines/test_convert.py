"""WI-2: RapidOCR-shaped raw output -> OcrResult conversion and score filtering."""

import json
import math
import re
import subprocess
import sys

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from snapocr.engines.convert import to_result
from snapocr.engines.errors import EngineRuntimeError
from snapocr.engines.types import OcrResult, TextBlock


def f32(x: float) -> float:
    return float(np.float32(x))


def assert_plain_python(value: object) -> None:
    """Recursively assert no numpy type survives anywhere in the result."""
    if isinstance(value, OcrResult):
        assert type(value.blocks) is tuple
        for block in value.blocks:
            assert_plain_python(block)
    elif isinstance(value, TextBlock):
        assert type(value.text) is str
        assert type(value.score) is float
        assert type(value.box) is tuple
        for point in value.box:
            assert type(point) is tuple
            for c in point:
                assert type(c) is float
    else:  # pragma: no cover - helper misuse
        raise AssertionError(f"unexpected {type(value)!r}")


# ---------------------------------------------------------------- examples

SAMPLE_BOXES = [
    [[12.0, 8.5], [310.25, 8.5], [310.25, 40.7], [12.0, 40.7]],
    [[12.3, 52.0], [268.0, 52.0], [268.0, 83.1], [12.3, 83.1]],
    [[14.0, 96.6], [220.9, 96.6], [220.9, 128.0], [14.0, 128.0]],
]
SAMPLE_TXTS = ("使用Python3截图识别，", "自动复制到剪贴板。", "Hello OCR 2026")
SAMPLE_SCORES = [0.997, 0.999, 0.983]


def test_measured_sample_converts_exactly():
    boxes = np.array(SAMPLE_BOXES, dtype=np.float32)
    scores = np.array(SAMPLE_SCORES, dtype=np.float32)

    result = to_result(boxes, SAMPLE_TXTS, scores, 0.5)

    expected = OcrResult(
        (
            TextBlock(
                "使用Python3截图识别，",
                (
                    (f32(12.0), f32(8.5)),
                    (f32(310.25), f32(8.5)),
                    (f32(310.25), f32(40.7)),
                    (f32(12.0), f32(40.7)),
                ),
                f32(0.997),
            ),
            TextBlock(
                "自动复制到剪贴板。",
                (
                    (f32(12.3), f32(52.0)),
                    (f32(268.0), f32(52.0)),
                    (f32(268.0), f32(83.1)),
                    (f32(12.3), f32(83.1)),
                ),
                f32(0.999),
            ),
            TextBlock(
                "Hello OCR 2026",
                (
                    (f32(14.0), f32(96.6)),
                    (f32(220.9), f32(96.6)),
                    (f32(220.9), f32(128.0)),
                    (f32(14.0), f32(128.0)),
                ),
                f32(0.983),
            ),
        )
    )
    assert result == expected
    assert_plain_python(result)


def test_measured_sample_from_nested_python_lists():
    result = to_result(SAMPLE_BOXES, list(SAMPLE_TXTS), SAMPLE_SCORES, 0.5)

    assert [b.text for b in result.blocks] == list(SAMPLE_TXTS)
    assert [b.score for b in result.blocks] == SAMPLE_SCORES
    assert [b.box for b in result.blocks] == [
        tuple(tuple(p) for p in box) for box in SAMPLE_BOXES
    ]
    assert_plain_python(result)


@pytest.mark.parametrize(
    "boxes, txts, scores",
    [
        (None, None, None),
        (np.empty((0, 4, 2), dtype=np.float32), (), np.empty((0,), dtype=np.float32)),
        ((), (), ()),
    ],
    ids=["all-none", "empty-arrays", "empty-tuples"],
)
def test_empty_inputs_return_empty_result(boxes, txts, scores):
    assert to_result(boxes, txts, scores, 0.5) == OcrResult(())


_PRESENT = {"boxes": [SAMPLE_BOXES[0]], "txts": ("a",), "scores": [0.9]}
_NONE_COMBOS = [
    ("boxes",),
    ("txts",),
    ("scores",),
    ("boxes", "txts"),
    ("boxes", "scores"),
    ("txts", "scores"),
]


@pytest.mark.parametrize("none_names", _NONE_COMBOS, ids=["+".join(c) for c in _NONE_COMBOS])
def test_partial_none_raises(none_names):
    args = {k: (None if k in none_names else v) for k, v in _PRESENT.items()}

    with pytest.raises(EngineRuntimeError) as excinfo:
        to_result(args["boxes"], args["txts"], args["scores"], 0.5)

    message = str(excinfo.value)
    for name in none_names:
        assert name in message


def _box():
    return [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]


@pytest.mark.parametrize(
    "lengths",
    [(3, 2, 3), (3, 3, 2), (2, 3, 3), (3, 3, 4)],
    ids=lambda t: "-".join(map(str, t)),
)
def test_length_mismatch_raises_with_all_three_lengths(lengths):
    nb, nt, ns = lengths
    boxes = [_box() for _ in range(nb)]
    txts = tuple("t" for _ in range(nt))
    scores = [0.9] * ns

    with pytest.raises(EngineRuntimeError) as excinfo:
        to_result(boxes, txts, scores, 0.5)

    assert re.search(rf"{nb}\D+{nt}\D+{ns}", str(excinfo.value))


def test_length_mismatch_with_numpy_containers_raises():
    boxes = np.zeros((3, 4, 2), dtype=np.float32)
    scores = np.full((2,), 0.9, dtype=np.float32)

    with pytest.raises(EngineRuntimeError) as excinfo:
        to_result(boxes, ("a", "b", "c"), scores, 0.5)

    assert re.search(r"3\D+3\D+2", str(excinfo.value))


@pytest.mark.parametrize(
    "boxes",
    [
        np.zeros((2, 3, 2), dtype=np.float32),
        np.zeros((2, 4, 3), dtype=np.float32),
        [[[0, 0], [1, 0], [1, 1]]] * 2,
        [[[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]]] * 2,
    ],
    ids=["array-N32", "array-N43", "list-N32", "list-N43"],
)
def test_wrong_box_shape_raises(boxes):
    with pytest.raises(EngineRuntimeError):
        to_result(boxes, ("a", "b"), [0.9, 0.9], 0.5)


@pytest.mark.parametrize(
    "boxes, txts, scores",
    [
        ([[[math.nan, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]], ("a",), [0.9]),
        ([_box()], ("a",), [math.nan]),
        ([_box()], ("a",), [1.0000001]),
        ([_box()], (None,), [0.9]),
    ],
    ids=["nan-coord", "nan-score", "score-above-one", "text-none"],
)
def test_invalid_values_raise_with_value_error_cause(boxes, txts, scores):
    with pytest.raises(EngineRuntimeError) as excinfo:
        to_result(boxes, txts, scores, 0.5)

    assert isinstance(excinfo.value.__cause__, ValueError)


@pytest.mark.parametrize(
    "min_score, scores, kept",
    [
        (0.5, [0.5, math.nextafter(0.5, 0.0)], [0.5]),
        (0.0, [0.0], [0.0]),
        (1.0, [1.0, math.nextafter(1.0, 0.0)], [1.0]),
    ],
    ids=["half", "zero", "one"],
)
def test_threshold_equal_kept_one_ulp_below_dropped(min_score, scores, kept):
    boxes = [_box() for _ in scores]
    txts = tuple(f"t{i}" for i in range(len(scores)))

    result = to_result(boxes, txts, scores, min_score)

    assert [b.score for b in result.blocks] == kept
    assert [b.text for b in result.blocks] == ["t0"]


def test_whitespace_only_text_dropped_others_verbatim():
    txts = ("", " ", "\t\n", "　", " a ", "​")
    boxes = [_box() for _ in txts]

    result = to_result(boxes, txts, [0.9] * len(txts), 0.5)

    assert [b.text for b in result.blocks] == [" a ", "​"]


def test_convert_import_pulls_no_heavy_deps():
    heavy = ["rapidocr", "onnxruntime", "numpy", "cv2"]
    code = (
        "import json, sys\n"
        "import snapocr.engines.convert\n"
        f"heavy = {heavy!r}\n"
        "print(json.dumps([m for m in heavy if m in sys.modules]))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-I", "-c", code], capture_output=True, text=True, timeout=60
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout.strip()) == []


# ---------------------------------------------------------------- properties

_whitespace = st.text(alphabet=" \t\n\r　 ", max_size=4)
_text = st.one_of(st.text(), st.text(), st.text(), _whitespace)
_coord = st.floats(-1e4, 1e4)
_raw_box = st.lists(st.tuples(_coord, _coord), min_size=4, max_size=4)
_raw_block = st.tuples(_text, _raw_box, st.floats(0, 1))
_raw_blocks = st.lists(_raw_block, min_size=0, max_size=12)
_threshold = st.floats(0, 1)


@st.composite
def engine_output(draw):
    """Return (raw_args, normalized_inputs) where raw_args feed to_result."""
    blocks = draw(_raw_blocks)
    as_array = draw(st.booleans())
    txts = tuple(t for t, _, _ in blocks)
    if as_array:
        boxes = np.array([b for _, b, _ in blocks], dtype=np.float32).reshape(len(blocks), 4, 2)
        scores = np.array([s for _, _, s in blocks], dtype=np.float32)
        norm_boxes = [tuple((f32(x), f32(y)) for x, y in b) for _, b, _ in blocks]
        norm_scores = [f32(s) for _, _, s in blocks]
    else:
        boxes = [[list(p) for p in b] for _, b, _ in blocks]
        scores = [s for _, _, s in blocks]
        norm_boxes = [tuple((float(x), float(y)) for x, y in b) for _, b, _ in blocks]
        norm_scores = list(scores)
    normalized = [TextBlock(t, b, s) for t, b, s in zip(txts, norm_boxes, norm_scores)]
    return (boxes, txts, scores), normalized


def reference(normalized, t):
    return tuple(b for b in normalized if b.score >= t and b.text.strip())


def is_subsequence(sub, seq) -> bool:
    it = iter(seq)
    return all(any(x == y for y in it) for x in sub)


@given(engine_output(), _threshold)
def test_matches_reference_model(data, t):
    (boxes, txts, scores), normalized = data

    result = to_result(boxes, txts, scores, t)

    assert result.blocks == reference(normalized, t)
    assert_plain_python(result)


@given(engine_output(), _threshold)
def test_output_is_order_preserving_subsequence_with_index_correspondence(data, t):
    (boxes, txts, scores), normalized = data

    result = to_result(boxes, txts, scores, t)

    i = 0
    for out in result.blocks:
        while i < len(normalized) and not (
            normalized[i].text == out.text
            and normalized[i].box == out.box
            and normalized[i].score == out.score
        ):
            i += 1
        assert i < len(normalized), f"{out!r} has no matching later input index"
        i += 1
        assert out.score >= t


@given(engine_output(), _threshold, _threshold)
def test_threshold_monotonic(data, a, b):
    (boxes, txts, scores), _ = data
    t1, t2 = min(a, b), max(a, b)

    r1 = to_result(boxes, txts, scores, t1)
    r2 = to_result(boxes, txts, scores, t2)

    assert len(r2.blocks) <= len(r1.blocks)
    assert is_subsequence(r2.blocks, r1.blocks)


@given(engine_output(), _threshold)
def test_refilter_is_idempotent(data, t):
    (boxes, txts, scores), _ = data
    r = to_result(boxes, txts, scores, t)

    r2 = to_result(
        [blk.box for blk in r.blocks],
        tuple(blk.text for blk in r.blocks),
        [blk.score for blk in r.blocks],
        t,
    )

    assert r2 == r


@given(engine_output(), st.one_of(st.just(0.0), _threshold, _threshold))
def test_drop_counts_conserved(data, t):
    (boxes, txts, scores), normalized = data
    n = len(normalized)

    out = to_result(boxes, txts, scores, t).blocks

    dropped = sum(1 for b in normalized if b.score < t or not b.text.strip())
    assert len(out) + dropped == n
    if t == 0.0:
        assert len(out) == sum(1 for b in normalized if b.text.strip())
