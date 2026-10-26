"""F4 WI-2: base_url loopback validation and TranslatorConfig (F4-6, D2, matrix Q3/Q4/Q16)."""

import dataclasses
import math
from dataclasses import FrozenInstanceError, fields

import pytest
from hypothesis import given
from hypothesis import strategies as st

from snapocr.translators.config import Endpoint, TranslatorConfig, parse_base_url
from snapocr.translators.errors import TranslatorConfigError
from support.tr_strategies import ok_base_url, sampling_dicts, url_candidates

DEFAULT_TEMPLATE = "把下面的文本翻译成{target_language}，不要额外解释。\n\n{source_text}"


def _rejects(value, key="base_url"):
    with pytest.raises(TranslatorConfigError) as info:
        parse_base_url(value)
    assert info.value.key == key
    return info.value


# --- parse_base_url / Endpoint -------------------------------------------------


def test_parse_base_url_normalizes():
    assert parse_base_url("http://127.0.0.1:11434/") == Endpoint(
        "127.0.0.1", 11434, "http://127.0.0.1:11434"
    )
    ep = parse_base_url("http://127.0.0.1:8080")
    assert ep.port == 8080
    assert type(ep.port) is int


ATTACKS = [
    "http://localhost:11434",
    "http://[::1]:11434",
    "http://127.0.0.2:11434",
    "http://0.0.0.0:11434",
    "http://127.1:11434",
    "http://2130706433:11434",
    "http://0x7f.0.0.1:11434",
    "http://[::ffff:127.0.0.1]:11434",
    "http://127.0.0.1:11434@evil.com",
    "http://evil.com#@127.0.0.1:11434",
    "http://user@127.0.0.1:11434",
    "https://127.0.0.1:11434",
    "http://127.0.0.1",
    "http://127.0.0.1:11434/v1",
    "http://127.0.0.1:0",
    "http://127.0.0.1:65536",
    "127.0.0.1:11434",
    "",
    # Q4 additions
    "HTTP://127.0.0.1:11434",
    "http://127.0.0.1:011434",
    "http://127.0.0.1:11434\n",
    " http://127.0.0.1:11434 ",
    "http://127.0.0.1:11434//",
    "http://127.0.0.1:11434/v1/",
    "http://127.0.0.1:11434?x=1",
    "http://127.0.0.1:+1",
    "http://127.0.0.1:１１４３４",
    "http://127.0.0.1.evil.com:11434",
    None,
    b"http://127.0.0.1:11434",
    11434,
]


@pytest.mark.parametrize("value", ATTACKS, ids=repr)
def test_base_url_attack_table(value):
    _rejects(value)
    with pytest.raises(TranslatorConfigError) as info:
        TranslatorConfig(base_url=value)
    assert info.value.key == "base_url"


def test_base_url_fix_hints():
    for url in ["http://localhost:11434", "http://LOCALHOST:11434"]:
        assert "改成 127.0.0.1" in str(_rejects(url))
    for url in ["http://127.0.0.1:11434/v1", "http://127.0.0.1:11434/v1/"]:
        assert "不要带 /v1" in str(_rejects(url))
    msg = str(_rejects("http://127.0.0.2:11434"))
    assert "改成 127.0.0.1" not in msg
    assert "不要带 /v1" not in msg


def test_port_edges():
    assert parse_base_url("http://127.0.0.1:1").port == 1
    assert parse_base_url("http://127.0.0.1:65535").port == 65535
    for port in ["0", "65536", "99999", "100000"]:
        _rejects(f"http://127.0.0.1:{port}")


@pytest.mark.parametrize(
    "args",
    [
        ("10.0.0.1", 80, "http://10.0.0.1:80"),
        ("127.0.0.1", 0, "http://127.0.0.1:0"),
        ("127.0.0.1", 11434, "http://evil.com"),
        ("127.0.0.1", True, "http://127.0.0.1:1"),
    ],
)
def test_endpoint_rejects_non_loopback_construction(args):
    with pytest.raises(TranslatorConfigError) as info:
        Endpoint(*args)
    assert info.value.key == "base_url"


def test_endpoint_frozen():
    ep = parse_base_url("http://127.0.0.1:11434")
    for name, value in [("host", "10.0.0.1"), ("port", 80), ("url", "x")]:
        with pytest.raises(FrozenInstanceError):
            setattr(ep, name, value)
    with pytest.raises(TranslatorConfigError) as info:
        dataclasses.replace(ep, host="10.0.0.1")
    assert info.value.key == "base_url"
    cfg = TranslatorConfig()
    with pytest.raises(FrozenInstanceError):
        cfg.endpoint.host = "10.0.0.1"  # type: ignore[misc]


def _oracle_accepts(s) -> bool:
    if not isinstance(s, str):
        return False
    r = s.removesuffix("/")
    prefix = "http://127.0.0.1:"
    if not r.startswith(prefix):
        return False
    p = r[len(prefix):]
    return p.isascii() and p.isdigit() and str(int(p)) == p and 1 <= int(p) <= 65535


@given(url_candidates() | st.text() | st.binary() | st.none() | st.integers())
def test_parse_base_url_total_and_loopback_only(s):
    try:
        e = parse_base_url(s)
    except TranslatorConfigError as err:
        assert err.key == "base_url"
        assert not _oracle_accepts(s)
    else:
        assert e.host == "127.0.0.1"
        assert e.url == f"http://127.0.0.1:{e.port}"
        assert _oracle_accepts(s)


@given(ok_base_url())
def test_accepts_every_valid_port(pair):
    url, p = pair
    assert parse_base_url(url) == Endpoint("127.0.0.1", p, f"http://127.0.0.1:{p}")


@given(ok_base_url().map(lambda pair: pair[0]) | url_candidates())
def test_normalization_roundtrip(s):
    try:
        e = parse_base_url(s)
    except TranslatorConfigError:
        return
    assert parse_base_url(e.url) == e
    assert TranslatorConfig(base_url=e.url).endpoint == e


# --- TranslatorConfig ----------------------------------------------------------


def _config_rejects(key, **kw):
    with pytest.raises(TranslatorConfigError) as info:
        TranslatorConfig(**kw)
    assert info.value.key == key
    return info.value


def test_defaults_match_prd():
    c = TranslatorConfig()
    assert c.base_url == "http://127.0.0.1:11434"
    assert c.model == "hy-mt2:7b"
    assert c.timeout_s == 60.0
    assert c.target_lang == "auto"
    assert c.direction_threshold == 0.3
    assert c.prompt_template == DEFAULT_TEMPLATE
    assert dict(c.sampling) == {"temperature": 0.7, "top_p": 0.8}
    assert c.max_input_chars == 4000
    assert c.endpoint == Endpoint("127.0.0.1", 11434, "http://127.0.0.1:11434")


def test_field_set_has_no_network_escape():
    by_name = {f.name: f for f in fields(TranslatorConfig)}
    assert set(by_name) == {
        "base_url",
        "model",
        "timeout_s",
        "target_lang",
        "direction_threshold",
        "prompt_template",
        "sampling",
        "max_input_chars",
        "endpoint",
    }
    assert by_name["endpoint"].init is False
    with pytest.raises(TypeError):
        TranslatorConfig(allow_remote=True)  # type: ignore[call-arg]


def test_timeout_edges():
    for ok in [0.001, 5, 600]:
        assert TranslatorConfig(timeout_s=ok).timeout_s == ok
    for bad in [0, -1, 600.0001, math.inf, math.nan, True, "60"]:
        _config_rejects("timeout_s", timeout_s=bad)


def test_threshold_edges():
    for ok in [1e-12, 0.3, 1]:
        assert TranslatorConfig(direction_threshold=ok).direction_threshold == ok
    for bad in [0, 1.0000001, math.nan, math.inf, True, "0.3"]:
        _config_rejects("direction_threshold", direction_threshold=bad)


def test_model_rules():
    for ok in ["hy-mt2:7b", "qwen2.5:7b-instruct"]:
        assert TranslatorConfig(model=ok).model == ok
    for bad in ["", "   ", " hy-mt2:7b", "hy-mt2:7b\n", "a\x00b", "a\tb", None, 7]:
        _config_rejects("model", model=bad)


def test_model_rejects_ollama_cloud():
    # Review C1: Ollama forwards "*-cloud" / ":cloud" models to ollama.com.
    for bad in [
        "gpt-oss:120b-cloud",
        "glm-4.6:cloud",
        "GPT-OSS:120B-CLOUD",
        "m:Cloud",
        "library/x:1b-cloud",
    ]:
        with pytest.raises(TranslatorConfigError) as info:
            TranslatorConfig(model=bad)
        assert info.value.key == "model"
        assert "cloud" in str(info.value)
    for ok in ["gpt-oss-cloud", "cloud", "cloudy:7b", "m:cloudy", "m:7b-cloudx", "m:cloud7b"]:
        assert TranslatorConfig(model=ok).model == ok


def test_target_lang_values():
    for ok in ["auto", "zh", "en"]:
        assert TranslatorConfig(target_lang=ok).target_lang == ok
    for bad in ["AUTO", "fr", "", None]:
        _config_rejects("target_lang", target_lang=bad)


def test_prompt_template_placeholders():
    for ok in ["{source_text}", "x{target_language}y{source_text}", "{}{0}{source_text}"]:
        assert TranslatorConfig(prompt_template=ok).prompt_template == ok
    for bad in [
        "无占位符",
        "{source_text}{source_text}",
        "{target_language}{target_language}{source_text}",
        "{ source_text }",
        123,
    ]:
        _config_rejects("prompt_template", prompt_template=bad)


def test_sampling_whitelist_and_types():
    accepted = [
        {},
        {"temperature": 0},
        {"temperature": 2},
        {"top_p": 1},
        {"max_tokens": 1},
        {"seed": -5},
        {"stop": "\n"},
        {"stop": ["a", "b"]},
        {"presence_penalty": -2},
        {"frequency_penalty": 2},
    ]
    for ok in accepted:
        TranslatorConfig(sampling=ok)
    for name in ["top_k", "repeat_penalty", "model", "messages", "stream"]:
        err = _config_rejects("sampling", sampling={name: 1})
        assert name in str(err)
    rejected = [
        {"temperature": True},
        {"temperature": "0.7"},
        {"temperature": math.nan},
        {"temperature": 2.01},
        {"temperature": -0.1},
        {"top_p": 1.01},
        {"max_tokens": 0},
        {"max_tokens": 1.5},
        {"max_tokens": True},
        {"seed": 1.0},
        {"stop": ["a", 1]},
        {"stop": 5},
    ]
    for bad in rejected:
        _config_rejects("sampling", sampling=bad)
    for bad in [["temperature"], None]:
        _config_rejects("sampling", sampling=bad)


_REAL_RANGES = {
    "temperature": (0, 2),
    "top_p": (0, 1),
    "presence_penalty": (-2, 2),
    "frequency_penalty": (-2, 2),
}


def _sampling_reject_cases():
    for name, (lo, hi) in _REAL_RANGES.items():
        for v in [True, False, math.nan, math.inf, -math.inf, "1", None, lo - 1e-9, hi + 1e-9]:
            yield name, v
    for name in ["seed", "max_tokens"]:
        for v in [True, False, 1.0, "1", None]:
            yield name, v
    for v in [None, b"x", [b"x"], 1]:
        yield "stop", v


@pytest.mark.parametrize(("name", "value"), list(_sampling_reject_cases()), ids=repr)
def test_sampling_reject_matrix(name, value):
    err = _config_rejects("sampling", sampling={name: value})
    assert name in str(err)


@pytest.mark.parametrize("name", list(_REAL_RANGES))
def test_sampling_real_bounds_accepted(name):
    lo, hi = _REAL_RANGES[name]
    assert TranslatorConfig(sampling={name: lo}).sampling[name] == lo
    assert TranslatorConfig(sampling={name: hi}).sampling[name] == hi


def test_max_input_chars_edges():
    for ok in [1, 4000]:
        assert TranslatorConfig(max_input_chars=ok).max_input_chars == ok
    for bad in [0, -1, 1.0, True]:
        _config_rejects("max_input_chars", max_input_chars=bad)


def test_config_immutable_and_isolated():
    stop = ["a", "b"]
    raw = {"temperature": 0.5, "stop": stop}
    cfg = TranslatorConfig(sampling=raw)
    for f in fields(TranslatorConfig):
        with pytest.raises(FrozenInstanceError):
            setattr(cfg, f.name, getattr(cfg, f.name))
    with pytest.raises(TypeError):
        cfg.sampling["temperature"] = 1  # type: ignore[index]
    raw["temperature"] = 1.5
    raw["seed"] = 3
    stop.append("c")
    assert dict(cfg.sampling) == {"temperature": 0.5, "stop": ("a", "b")}
    assert cfg.sampling["stop"] == ("a", "b")


def test_replace_revalidates():
    cfg = TranslatorConfig()
    with pytest.raises(TranslatorConfigError):
        dataclasses.replace(cfg, base_url="http://localhost:1")
    assert dataclasses.replace(cfg, base_url="http://127.0.0.1:9/").endpoint.port == 9


_VALID = {
    "base_url": st.sampled_from(["http://127.0.0.1:11434", "http://127.0.0.1:1/"]),
    "model": st.sampled_from(["hy-mt2:7b", "m"]),
    "timeout_s": st.sampled_from([0.5, 60, 600]),
    "target_lang": st.sampled_from(["auto", "zh", "en"]),
    "direction_threshold": st.sampled_from([0.01, 0.3, 1]),
    "prompt_template": st.sampled_from(["{source_text}", "{target_language}:{source_text}"]),
    "sampling": sampling_dicts(),
    "max_input_chars": st.sampled_from([1, 4000]),
}
_INVALID = {
    "base_url": st.sampled_from(["http://localhost:11434", "", None]),
    "model": st.sampled_from(["", " m", None]),
    "timeout_s": st.sampled_from([0, math.nan, True]),
    "target_lang": st.sampled_from(["fr", None]),
    "direction_threshold": st.sampled_from([0, 2, math.nan]),
    "prompt_template": st.sampled_from(["x", "{source_text}{source_text}", None]),
    "sampling": st.sampled_from([{"top_k": 1}, {"temperature": 3}, None]),
    "max_input_chars": st.sampled_from([0, 1.0, True]),
}


@given(st.data())
def test_config_construction_total(data):
    bad_field = data.draw(st.none() | st.sampled_from(sorted(_VALID)))
    kw = {
        name: data.draw(_INVALID[name] if name == bad_field else _VALID[name])
        for name in _VALID
    }
    if bad_field is None:
        cfg = TranslatorConfig(**kw)
        for name, value in kw.items():
            got = getattr(cfg, name)
            if name == "sampling":
                expected = {
                    k: tuple(v) if isinstance(v, list) else v for k, v in value.items()
                }
                assert dict(got) == expected
            else:
                assert got == value
    else:
        with pytest.raises(TranslatorConfigError) as info:
            TranslatorConfig(**kw)
        assert info.value.key == bad_field
