"""F4 WI-5: response parsing and HTTP failure classification (F4-3, F4-5, D7, matrix Q9/Q10/Q12)."""

import json
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from snapocr.translators.errors import ErrorContext, TranslationError, TranslationErrorKind
from snapocr.translators.protocol import parse_chat_response
from support.leakcheck import no_leak
from support.tr_strategies import MISSING, error_body, marker, ok

K = TranslationErrorKind
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "translators"
CTX = ErrorContext("http://127.0.0.1:11434", "hy-mt2:7b")
SENTENCE = "The weather is very nice today."


def _fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _parse(status, body):
    return parse_chat_response(status, body, ctx=CTX)


def _fails(status, body, kind):
    with pytest.raises(TranslationError) as info:
        _parse(status, body)
    err = info.value
    assert err.kind is kind
    assert CTX.base_url in str(err)
    assert CTX.model in str(err)
    return err


def _dumps(obj) -> bytes:
    return json.dumps(obj).encode()


def test_parse_fixture_ok():
    assert _parse(200, _fixture("chat_ok.json")) == SENTENCE
    assert _parse(200, _fixture("chat_think.json")) == SENTENCE


BAD_SHAPES = [
    b"not json",
    b"",
    b"[]",
    b'"s"',
    b"{}",
    _dumps({"choices": []}),
    _dumps({"choices": {}}),
    _dumps({"choices": [1]}),
    _dumps({"choices": [{}]}),
    _dumps({"choices": [{"message": "x"}]}),
    _dumps({"choices": [{"message": {}}]}),
    ok(None),
    ok(5),
    ok(["x"]),
    b"\xff\xfe{}",
    b"\xef\xbb\xbf" + ok("Hi"),
]


@pytest.mark.parametrize("body", BAD_SHAPES, ids=repr)
def test_bad_response_shapes(body):
    err = _fails(200, body, K.BAD_RESPONSE)
    assert err.status is None


@pytest.mark.parametrize(
    "body",
    [
        b'{"choices":[{"message":{"content":"Hi\xff"}}]}',
        b'{"choices":[{"message":{"content":"Hi\xed\xa0\x80"}}]}',
    ],
    ids=repr,
)
def test_bad_response_invalid_utf8(body):
    err = _fails(200, body, K.BAD_RESPONSE)
    assert err.detail == "not UTF-8"


@pytest.mark.parametrize("finish", ["stop", MISSING, None, "tool_calls", 5, "LENGTH"], ids=repr)
def test_finish_reason_normal_values(finish):
    assert _parse(200, ok("Hi", finish_reason=finish)) == "Hi"


def test_finish_reason_length_is_truncated():
    _fails(200, ok("Hi", finish_reason="length"), K.TRUNCATED)
    _fails(200, _fixture("chat_length.json"), K.TRUNCATED)


def test_precedence():
    _fails(200, ok("", finish_reason="length"), K.TRUNCATED)
    _fails(200, ok(None, finish_reason="length"), K.BAD_RESPONSE)
    _fails(200, ok("<think>x</think>"), K.EMPTY_OUTPUT)
    _fails(200, ok("   "), K.EMPTY_OUTPUT)


STATUS_CASES = [
    (404, _fixture("error_model_not_found.json"), K.MODEL_NOT_FOUND),
    (404, _dumps({"error": "model 'x' not found"}), K.MODEL_NOT_FOUND),
    (404, _dumps({"error": {"message": "Model missing"}}), K.MODEL_NOT_FOUND),
    (404, b"<html><h1>404 Not Found</h1></html>", K.HTTP_STATUS),
    (404, _dumps({"error": {"message": "page not found"}}), K.HTTP_STATUS),
    (404, _dumps({"error": {"code": 1}}), K.HTTP_STATUS),
    (404, _dumps({"error": {"message": 5}}), K.HTTP_STATUS),
    (404, b"\xff", K.HTTP_STATUS),
    (404, b"[]", K.HTTP_STATUS),
    (500, _dumps({"error": {"message": "model crashed"}}), K.HTTP_STATUS),
    (301, b"", K.HTTP_STATUS),
    (307, b"", K.HTTP_STATUS),
    (201, ok("Hi"), K.HTTP_STATUS),
    (100, b"", K.HTTP_STATUS),
]


@pytest.mark.parametrize(("status", "body", "kind"), STATUS_CASES, ids=repr)
def test_status_classification(status, body, kind):
    err = _fails(status, body, kind)
    assert err.status == status
    assert f"HTTP {status}" in str(err)


def test_deeply_nested_json():
    err = _fails(200, b"[" * 100_000, K.BAD_RESPONSE)
    assert err.detail == "not JSON"
    assert _fails(404, b"[" * 100_000, K.HTTP_STATUS).status == 404
    _fails(404, b'{"error":' * 50_000, K.HTTP_STATUS)


json_values = st.recursive(
    st.none() | st.booleans() | st.floats() | st.integers() | st.text(),
    lambda children: st.lists(children, max_size=4)
    | st.dictionaries(st.text(max_size=8), children, max_size=4),
    max_leaves=12,
)
choice_like = st.fixed_dictionaries(
    {"choices": st.lists(st.fixed_dictionaries({"message": json_values}), max_size=2)}
)
any_body = st.one_of(
    st.binary(max_size=200),
    json_values.map(lambda v: json.dumps(v).encode()),
    choice_like.map(lambda v: json.dumps(v).encode()),
    marker().flatmap(error_body).map(lambda pair: pair[1]),
)


@given(st.integers(100, 599), any_body)
def test_classification_total(status, body):
    try:
        out = _parse(status, body)
    except TranslationError as err:
        assert CTX.base_url in str(err)
        assert CTX.model in str(err)
        if status != 200:
            assert err.kind in {K.HTTP_STATUS, K.MODEL_NOT_FOUND}
            assert err.status == status
        if err.kind is K.MODEL_NOT_FOUND:
            assert status == 404
    else:
        assert status == 200
        assert isinstance(out, str)
        assert out


tag_free = st.text().filter(
    lambda s: "<think>" not in s and "</think>" not in s and s.strip() != ""
)


@given(
    tag_free,
    st.sampled_from([MISSING, None, "stop"]),
    st.dictionaries(st.sampled_from(["usage", "x_extra", "system_fingerprint"]), json_values),
)
def test_success_oracle(content, finish, extra):
    assert _parse(200, ok(content, finish_reason=finish, **extra)) == content.strip()


@given(marker().flatmap(lambda m: st.tuples(st.just(m), error_body(m))))
def test_error_never_leaks_body(case):
    m, (status, body) = case
    with pytest.raises(TranslationError) as info:
        _parse(status, body)
    no_leak(info.value, m)
