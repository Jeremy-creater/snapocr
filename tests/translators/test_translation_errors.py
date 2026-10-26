"""F4 WI-1: TranslationError, ErrorContext, TranslatorConfigError (matrix Q7-Q9)."""

from dataclasses import FrozenInstanceError

import pytest
from hypothesis import given
from hypothesis import strategies as st

from snapocr.translators.errors import (
    ErrorContext,
    TranslationError,
    TranslationErrorKind,
    TranslatorConfigError,
)

BASE = "http://127.0.0.1:11434"
MODEL = "hy-mt2:7b"

# Q8: hint keywords per kind (only keywords are asserted, not whole sentences).
HINT_KEYWORDS = {
    "UNREACHABLE": ["ollama serve"],
    "TIMEOUT": ["timeout_s"],
    "CONNECTION": ["重启 Ollama"],
    "MODEL_NOT_FOUND": ["ollama list", "ollama create hy-mt2:7b -f docs/hy-mt2-7b.Modelfile"],
    "HTTP_STATUS": ["Ollama 日志"],
    "BAD_RESPONSE": ["/v1/chat/completions"],
    "EMPTY_OUTPUT": ["prompt_template"],
    "TRUNCATED": ["max_tokens"],
    "INPUT_TOO_LONG": ["max_input_chars"],
}

ALL_KINDS = list(TranslationErrorKind)


def _err(kind, **kw):
    kw.setdefault("base_url", BASE)
    kw.setdefault("model", MODEL)
    return TranslationError(kind, **kw)


def test_kind_members():
    assert {k.name for k in TranslationErrorKind} == set(HINT_KEYWORDS)


@pytest.mark.parametrize("kind", ALL_KINDS, ids=lambda k: k.name)
def test_message_per_kind(kind):
    s = str(_err(kind, detail="d"))
    assert s.startswith(
        f"translation failed [{kind.name}]: d (base_url={BASE}, model={MODEL}); fix: "
    )
    for keyword in HINT_KEYWORDS[kind.name]:
        assert keyword in s


def test_message_without_detail():
    s = str(_err(TranslationErrorKind.TIMEOUT))
    prefix = f"translation failed [TIMEOUT] (base_url={BASE}, model={MODEL}); fix: "
    assert s.startswith(prefix)
    assert len(s) > len(prefix)
    assert "]:" not in s


def test_hints_distinct_and_marker_free():
    messages = [str(_err(k)) for k in ALL_KINDS]
    hints = [m.split("; fix: ", 1)[1] for m in messages]
    assert len(set(hints)) == len(ALL_KINDS)
    assert all("ZQXJ" not in m for m in messages)


def test_attributes():
    e = _err(TranslationErrorKind.HTTP_STATUS, detail="HTTP 500", status=500)
    assert e.kind is TranslationErrorKind.HTTP_STATUS
    assert (e.base_url, e.model, e.detail, e.status) == (BASE, MODEL, "HTTP 500", 500)
    assert isinstance(e, Exception)
    assert _err(TranslationErrorKind.TIMEOUT).status is None


def test_constructor_rejects_source_text():
    with pytest.raises(TypeError):
        TranslationError(  # type: ignore[call-arg]
            TranslationErrorKind.TIMEOUT, base_url=BASE, model=MODEL, text="原文"
        )


def test_constructor_requires_keyword_context():
    with pytest.raises(TypeError):
        TranslationError(TranslationErrorKind.TIMEOUT, BASE, MODEL)  # type: ignore[misc]


def test_constructor_rejects_non_kind():
    with pytest.raises(TypeError):
        TranslationError("TIMEOUT", base_url=BASE, model=MODEL)  # type: ignore[arg-type]


@given(
    st.sampled_from(ALL_KINDS),
    st.text(min_size=1),
    st.text(min_size=1),
    st.text(),
    st.none() | st.integers(100, 599),
)
def test_message_contains_context_for_all_inputs(kind, base_url, model, detail, status):
    err = TranslationError(kind, base_url=base_url, model=model, detail=detail, status=status)
    s = str(err)
    assert base_url in s
    assert model in s
    assert f"[{kind.name}]" in s
    for keyword in HINT_KEYWORDS[kind.name]:
        assert keyword in s
    assert err.args == (s,)
    assert str(err) == s


def test_error_context_frozen():
    ctx = ErrorContext("u", "m")
    assert (ctx.base_url, ctx.model) == ("u", "m")
    with pytest.raises(FrozenInstanceError):
        ctx.model = "x"  # type: ignore[misc]


def test_config_error_is_value_error_with_key():
    e = TranslatorConfigError("bad", key="timeout_s")
    assert isinstance(e, ValueError)
    assert e.key == "timeout_s"
    assert "timeout_s" in str(e)
    assert "bad" in str(e)
