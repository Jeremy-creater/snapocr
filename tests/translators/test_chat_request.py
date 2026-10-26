"""F4 WI-4: prompt rendering and chat request construction (F4-2, D8, matrix Q5)."""

import json

import pytest
from hypothesis import given
from hypothesis import strategies as st

from snapocr.translators.config import TranslatorConfig
from snapocr.translators.protocol import build_chat_request, render_prompt
from support.tr_strategies import sampling_dicts, source_text, template

PREFIX_EN = "把下面的文本翻译成英语，不要额外解释。\n\n"
PREFIX_ZH = "把下面的文本翻译成中文，不要额外解释。\n\n"
NAMES = {"en": "英语", "zh": "中文"}
langs = st.sampled_from(["zh", "en"])


def _body(req):
    return json.loads(req.body)


def test_request_exact_dict_en():
    req = build_chat_request(TranslatorConfig(), "en", "你好")
    assert req.path == "/v1/chat/completions"
    assert dict(req.headers) == {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    assert _body(req) == {
        "model": "hy-mt2:7b",
        "messages": [{"role": "user", "content": PREFIX_EN + "你好"}],
        "stream": False,
        "temperature": 0.7,
        "top_p": 0.8,
    }


def test_request_exact_dict_zh_no_sampling():
    body = _body(build_chat_request(TranslatorConfig(sampling={}), "zh", "Hello"))
    assert body["messages"][0]["content"] == PREFIX_ZH + "Hello"
    assert set(body) == {"model", "messages", "stream"}


@pytest.mark.parametrize(
    "s",
    [
        "{source_text}",
        "{target_language}",
        "{}",
        "{0}",
        "%s",
        '"',
        "\\",
        "a\nb",
        "😀",
        " ",
        "\x00",
        "\ud800",
    ],
    ids=repr,
)
def test_render_special_characters_literal(s):
    cfg = TranslatorConfig()
    assert render_prompt(cfg.prompt_template, "en", s) == PREFIX_EN + s
    assert _body(build_chat_request(cfg, "en", s))["messages"][0]["content"] == PREFIX_EN + s


def test_render_template_order():
    assert (
        render_prompt("{source_text} → {target_language}", "en", "{target_language}")
        == "{target_language} → 英语"
    )
    assert render_prompt("{source_text}", "zh", "x") == "x"


def _reject_constant(name):
    raise AssertionError(f"non-standard JSON constant {name}")


def test_body_strict_ascii_json():
    req = build_chat_request(TranslatorConfig(), "en", "你好😀")
    assert req.body.isascii()
    body = json.loads(req.body, parse_constant=_reject_constant)
    assert body["stream"] is False


@pytest.mark.parametrize("lang", ["fr", None, "auto"])
def test_target_lang_guard(lang):
    with pytest.raises(ValueError):
        render_prompt("{source_text}", lang, "x")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        build_chat_request(TranslatorConfig(), lang, "x")  # type: ignore[arg-type]


@given(template(), langs, source_text())
def test_render_roundtrip_property(tps, lang, s):
    t, p, suffix = tps
    name = NAMES[lang]
    expected = (
        p.replace("{target_language}", name) + s + suffix.replace("{target_language}", name)
    )
    assert render_prompt(t, lang, s) == expected
    req = build_chat_request(TranslatorConfig(prompt_template=t), lang, s)
    assert _body(req)["messages"][0]["content"] == _json_canonical(expected)


def _json_canonical(s: str) -> str:
    """Join adjacent high+low lone surrogates into one astral character.

    JSON writes the two code points "\\ud800\\udc00" and the single U+10000 as
    the same escape pair, and decoding always joins it, so the round trip can
    only hold up to this canonical form (matrix r1.1, Q5). The bytes sent are
    identical either way.
    """
    return s.encode("utf-16-le", "surrogatepass").decode("utf-16-le", "surrogatepass")


def test_json_canonical_joins_only_pairs():
    assert _json_canonical("𐀀") == "\U00010000"
    assert _json_canonical("\ud800x\udc00") == "\ud800x\udc00"
    assert _json_canonical("\udc00\ud800") == "\udc00\ud800"
    content = _body(build_chat_request(TranslatorConfig(), "en", "𐀀"))
    assert content["messages"][0]["content"] == PREFIX_EN + "\U00010000"


@given(langs, source_text(), source_text())
def test_only_content_depends_on_source(lang, s1, s2):
    cfg = TranslatorConfig()
    r1, r2 = build_chat_request(cfg, lang, s1), build_chat_request(cfg, lang, s2)
    b1, b2 = _body(r1), _body(r2)
    c1 = b1["messages"][0].pop("content")
    c2 = b2["messages"][0].pop("content")
    assert b1 == b2
    assert (c1 == c2) == (_json_canonical(s1) == _json_canonical(s2))
    assert dict(r1.headers) == dict(r2.headers)
    assert r1.path == r2.path


@given(langs, source_text())
def test_deterministic_bytes(lang, s):
    a = build_chat_request(TranslatorConfig(), lang, s).body
    assert build_chat_request(TranslatorConfig(), lang, s).body == a
    cfg = TranslatorConfig(sampling={"seed": 1, "temperature": 0})
    same = TranslatorConfig(sampling={"seed": 1, "temperature": 0})
    assert build_chat_request(cfg, lang, s).body == build_chat_request(same, lang, s).body


@given(sampling_dicts(), langs)
def test_sampling_merged_not_overriding(sampling, lang):
    cfg = TranslatorConfig(sampling=sampling)
    body = _body(build_chat_request(cfg, lang, "x"))
    assert set(body) == {"model", "messages", "stream"} | set(sampling)
    for k, v in sampling.items():
        assert body[k] == (list(v) if isinstance(v, (list, tuple)) else v)
    assert body["model"] == "hy-mt2:7b"
    assert body["stream"] is False


def test_request_uses_config_model():
    assert _body(build_chat_request(TranslatorConfig(model="m-x:1"), "en", "a"))["model"] == "m-x:1"
