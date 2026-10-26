"""F4 WI-7: OpenAICompatTranslator end to end against the fake service (F4-1..F4-6, matrix Q13-Q17)."""

import json
import logging
import socket
import threading
import time
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import snapocr.translators as pkg
from snapocr.translators import config as config_mod
from snapocr.translators import direction as direction_mod
from snapocr.translators import errors as errors_mod
from snapocr.translators import openai_compat as compat_mod
from snapocr.translators import types as types_mod
from snapocr.translators.config import TranslatorConfig
from snapocr.translators.direction import detect_target_lang
from snapocr.translators.errors import TranslationError, TranslationErrorKind
from snapocr.translators.openai_compat import OpenAICompatTranslator
from snapocr.translators.protocol import build_chat_request
from snapocr.translators.types import TranslationResult, Translator
from support.fake_openai_server import Reply, echo
from support.leakcheck import no_leak
from support.tr_strategies import marker, neutral, ok, script_text

pytestmark = pytest.mark.usefixtures("loopback_guard")

K = TranslationErrorKind
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "translators"
LOGGER = "snapocr.translators"
M = "ZQXJ9a8b7c6d5e4f"
PREFIX_EN = "把下面的文本翻译成英语，不要额外解释。\n\n"
PREFIX_ZH = "把下面的文本翻译成中文，不要额外解释。\n\n"


def EN(s):
    return PREFIX_EN + s


def ZH(s):
    return PREFIX_ZH + s


def _fixture(name):
    return (FIXTURES / name).read_bytes()


def _fresh(fake):
    fake.reset()
    return fake


def cfg(fake, **kw):
    kw.setdefault("timeout_s", 2.0)
    return TranslatorConfig(base_url=fake.base_url, **kw)


def _translate(fake, text, **kw):
    return OpenAICompatTranslator(cfg(fake, **kw)).translate(text)


def _sent(fake, i=0):
    return json.loads(fake.requests[i].body)


def _content(fake, i=0):
    return _sent(fake, i)["messages"][0]["content"]


# --- success paths -------------------------------------------------------------


def test_translate_zh_to_en(fake_server):
    fake = _fresh(fake_server)
    fake.script(Reply(body=_fixture("chat_ok.json")))
    result = _translate(fake, "今天天气很好")
    assert result == TranslationResult("The weather is very nice today.", "en", False)
    assert _sent(fake) == json.loads(build_chat_request(cfg(fake), "en", "今天天气很好").body)
    assert "英语" in _content(fake)


def test_translate_en_to_zh_with_think(fake_server):
    fake = _fresh(fake_server)
    fake.script(Reply(body=ok("<think>\n</think>\n\n今天天气很好。")))
    assert _translate(fake, "Hello world") == TranslationResult("今天天气很好。", "zh", False)
    assert "中文" in _content(fake)


def test_request_uses_every_config_field(fake_server):
    fake = _fresh(fake_server)
    fake.script(Reply(body=ok("x")))
    _translate(
        fake,
        "使用 Python3 截图",
        model="qwen2.5:7b-instruct",
        prompt_template="T[{target_language}]{source_text}",
        sampling={"temperature": 0, "seed": 1},
        direction_threshold=0.5,
    )
    assert _sent(fake) == {
        "model": "qwen2.5:7b-instruct",
        "messages": [{"role": "user", "content": "T[中文]使用 Python3 截图"}],
        "stream": False,
        "temperature": 0,
        "seed": 1,
    }


def test_source_sent_verbatim(fake_server):
    fake = _fresh(fake_server)
    fake.script(Reply(body=ok("x")))
    _translate(fake, "  Hello\n world \t")
    assert _content(fake) == ZH("  Hello\n world \t")


# --- inputs that never reach the service -----------------------------------------


@pytest.mark.parametrize("target", ["auto", "zh", "en"])
@pytest.mark.parametrize("text", ["", " ", "\n\t", "　", " " * 5000], ids=repr)
def test_blank_inputs_no_request(fake_server, target, text):
    fake = _fresh(fake_server)
    assert _translate(fake, text, target_lang=target) == TranslationResult("", None, True)
    assert fake.requests == []


@pytest.mark.parametrize("text", ["123 !!", "  123 !! ", "😀", "１２３"])
def test_no_letter_inputs_skipped(fake_server, text):
    fake = _fresh(fake_server)
    assert _translate(fake, text) == TranslationResult(text, None, True)
    assert fake.requests == []


def test_fixed_target_sends_even_without_letters(fake_server):
    fake = _fresh(fake_server)
    fake.script(Reply(body=ok("123")))
    assert _translate(fake, "123", target_lang="zh") == TranslationResult("123", "zh", False)
    assert len(fake.requests) == 1
    assert "中文" in _content(fake)


def test_length_limit_edges(fake_server):
    fake = _fresh(fake_server)
    fake.respond_with(echo(jitter_s=(0, 0)))
    _translate(fake, "a" * 4000)
    _translate(fake, "😀" * 4000, target_lang="en")
    assert len(fake.requests) == 2
    fake.reset()
    for text in ["a" * 4001, "😀" * 4001, "1" * 4001, "a" * 3999 + "  "]:
        with pytest.raises(TranslationError) as info:
            _translate(fake, text)
        assert info.value.kind is K.INPUT_TOO_LONG
        no_leak(info.value, text)
    assert fake.requests == []
    with pytest.raises(TranslationError) as info:
        _translate(fake, "abcd", max_input_chars=3)
    assert "4" in info.value.detail
    assert "3" in info.value.detail


def test_non_str_rejected(fake_server):
    fake = _fresh(fake_server)
    translator = OpenAICompatTranslator(cfg(fake))
    for bad in [None, b"hi", 123, ["a"]]:
        with pytest.raises(TypeError):
            translator.translate(bad)  # type: ignore[arg-type]
    for bad in [M.encode(), [M]]:
        with pytest.raises(TypeError) as info:
            translator.translate(bad)  # type: ignore[arg-type]
        no_leak(info.value, M)
    assert fake.requests == []


def test_constructor_rejects_non_config():
    for bad in [{"base_url": "http://127.0.0.1:1"}, None]:
        with pytest.raises(TypeError):
            OpenAICompatTranslator(bad)  # type: ignore[arg-type]


# --- failure paths -----------------------------------------------------------------

SECRET_SOURCE = "秘密" + M

ERROR_SCRIPTS = [
    ("timeout", Reply(body=ok("x"), delay_s=0.5), {"timeout_s": 0.1}, K.TIMEOUT),
    ("model-404", Reply(404, body=_fixture("error_model_not_found.json")), {}, K.MODEL_NOT_FOUND),
    ("500-echo", Reply(500, body=SECRET_SOURCE.encode()), {}, K.HTTP_STATUS),
    ("bad-json", Reply(body=b"{bad"), {}, K.BAD_RESPONSE),
    ("think-only", Reply(body=ok("<think>x</think>")), {}, K.EMPTY_OUTPUT),
    ("length", Reply(body=_fixture("chat_length.json")), {}, K.TRUNCATED),
    ("disconnect", Reply(close_after_request=True), {}, K.CONNECTION),
    ("oversize", Reply(body=b"x" * 1_048_577), {}, K.BAD_RESPONSE),
]


@pytest.mark.parametrize(
    ("reply", "kw", "kind"), [c[1:] for c in ERROR_SCRIPTS], ids=[c[0] for c in ERROR_SCRIPTS]
)
def test_error_paths_map_kind(fake_server, reply, kw, kind):
    fake = _fresh(fake_server)
    fake.script(reply)
    with pytest.raises(TranslationError) as info:
        _translate(fake, SECRET_SOURCE, **kw)
    err = info.value
    assert err.kind is kind
    assert fake.base_url in str(err)
    assert "hy-mt2:7b" in str(err)
    if kind is K.HTTP_STATUS:
        assert err.status == 500
    no_leak(err, M)
    assert len(fake.requests) == 1


def test_unreachable_end_to_end():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    base_url = f"http://127.0.0.1:{port}"
    translator = OpenAICompatTranslator(TranslatorConfig(base_url=base_url, timeout_s=10))
    start = time.monotonic()
    with pytest.raises(TranslationError) as info:
        translator.translate("你好" + M)
    err = info.value
    assert err.kind is K.UNREACHABLE
    assert base_url in str(err)
    assert "hy-mt2:7b" in str(err)
    assert "ollama serve" in str(err)
    no_leak(err, M)
    assert time.monotonic() - start < 8


def _echoing_failure(kind: str):
    def reply(rec):
        src = json.loads(rec.body)["messages"][0]["content"]
        if kind == "500":
            return Reply(500, body=src.encode())
        if kind == "404":
            return Reply(404, body=json.dumps({"error": {"message": f"model {src} not found"}}).encode())
        if kind == "bad-json":
            return Reply(body=b'{"choices": "' + src.encode())
        if kind == "think":
            return Reply(body=ok(f"<think>{src}</think>"))
        if kind == "length":
            return Reply(body=ok(src, finish_reason="length"))
        if kind == "raw":
            marker_line = src[src.index("ZQXJ"):][:16].encode("ascii", "ignore")
            return Reply(raw=marker_line + b"\r\n\r\n")
        return Reply(body=ok([src]))

    return reply


class _ListHandler(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record):
        self.records.append(record)


def _record_views(record):
    return [record.getMessage(), repr(vars(record)), logging.Formatter().format(record)]


def _inserted(s: str, m: str, pos: int) -> str:
    pos = min(pos, len(s))
    return s[:pos] + m + s[pos:]


@settings(max_examples=25, deadline=None)
@given(
    script_text(),
    marker(),
    st.integers(0, 60),
    st.sampled_from(["500", "404", "bad-json", "think", "length", "raw", "list"]),
)
def test_error_privacy_property(fake_server, base, m, pos, kind):
    fake = _fresh(fake_server)
    fake.respond_with(_echoing_failure(kind))
    source = _inserted(base, m, pos)
    logger = logging.getLogger(LOGGER)
    handler, old_level = _ListHandler(), logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    try:
        with pytest.raises(TranslationError) as info:
            _translate(fake, source)
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)
    no_leak(info.value, m)
    assert len(fake.requests) == 1
    assert handler.records
    for record in handler.records:
        for view in _record_views(record):
            assert m not in view


blank = st.text(alphabet=" \t\n\r　\x0b\x0c")


@settings(max_examples=50, deadline=None)
@given(st.one_of(blank, st.lists(neutral).map("".join)))
def test_skip_never_requests_property(fake_server, text):
    fake = _fresh(fake_server)
    result = _translate(fake, text)
    assert result.skipped is True
    assert result.target_lang is None
    assert result.text == ("" if not text.strip() else text)
    assert fake.requests == []


with_letter = script_text().filter(lambda s: detect_target_lang(s, 0.3) is not None)


@settings(max_examples=25, deadline=None)
@given(with_letter)
def test_result_target_matches_direction(fake_server, s):
    fake = _fresh(fake_server)
    fake.respond_with(echo(jitter_s=(0, 0)))
    result = _translate(fake, s)
    target = detect_target_lang(s, 0.3)
    assert result.target_lang == target
    assert result.skipped is False
    prompt = EN(s) if target == "en" else ZH(s)
    assert result.text == prompt.strip()
    assert _content(fake).startswith(PREFIX_EN) == (target == "en")


non_blank = script_text().filter(lambda s: s.strip() != "")


@settings(max_examples=25, deadline=None)
@given(non_blank, non_blank)
def test_fixed_target_metamorphic(fake_server, s1, s2):
    fake = _fresh(fake_server)
    fake.respond_with(echo(jitter_s=(0, 0)))
    translator = OpenAICompatTranslator(cfg(fake, target_lang="en"))
    translator.translate(s1)
    translator.translate(s2)
    b1, b2 = _sent(fake, 0), _sent(fake, 1)
    c1, c2 = b1["messages"][0].pop("content"), b2["messages"][0].pop("content")
    assert b1 == b2
    assert (c1, c2) == (EN(s1), EN(s2))


def test_concurrent_translations_not_crossed(fake_server):
    fake = _fresh(fake_server)
    fake.respond_with(echo())
    translator = OpenAICompatTranslator(cfg(fake))
    barrier = threading.Barrier(4)
    results: dict[tuple[int, int], TranslationResult] = {}
    errors: list[BaseException] = []

    def worker(i):
        try:
            for r in range(3):
                barrier.wait()
                results[(i, r)] = translator.translate(f"线程{i}第{r}轮 text")
        except BaseException as exc:  # surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(20)
    assert errors == []
    assert len(results) == 12
    for (i, r), result in results.items():
        assert result == TranslationResult(EN(f"线程{i}第{r}轮 text").strip(), "en", False)
    assert len(fake.requests) == 12
    assert fake.wait_closed() == 0


def test_logs_and_output_contain_no_text(fake_server, caplog, capfd):
    fake = _fresh(fake_server)
    m1, m2, m3 = "ZQXJaaaa1111", "ZQXJbbbb2222", "ZQXJcccc3333"
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    ok_source = "请翻译 " + m1
    fake.script(Reply(body=ok("translated " + m2)))
    assert _translate(fake, ok_source).text == "translated " + m2
    fake.respond_with(lambda rec: Reply(500, body=rec.body))
    with pytest.raises(TranslationError):
        _translate(fake, "失败 " + m3)
    out, err = capfd.readouterr()
    for secret in (m1, m2, m3):
        assert secret not in out
        assert secret not in err
        for record in caplog.records:
            for view in _record_views(record):
                assert secret not in view
    ours = [r for r in caplog.records if r.name == "snapocr.translators.openai_compat"]
    messages = [r.getMessage() for r in ours if r.levelno == logging.DEBUG]
    assert any(f"chars={len(ok_source)}" in msg for msg in messages)
    assert any("kind=HTTP_STATUS" in msg for msg in messages)
    assert all(r.levelno < logging.INFO for r in caplog.records if r.name.startswith(LOGGER))


def test_package_exports(loopback_guard):
    assert set(pkg.__all__) == {
        "Translator",
        "OpenAICompatTranslator",
        "TranslatorConfig",
        "TranslationResult",
        "TranslationError",
        "TranslationErrorKind",
        "TranslatorConfigError",
        "detect_target_lang",
    }
    origins = {
        "Translator": types_mod,
        "TranslationResult": types_mod,
        "OpenAICompatTranslator": compat_mod,
        "TranslatorConfig": config_mod,
        "TranslationError": errors_mod,
        "TranslationErrorKind": errors_mod,
        "TranslatorConfigError": errors_mod,
        "detect_target_lang": direction_mod,
    }
    for name, module in origins.items():
        assert getattr(pkg, name) is getattr(module, name)
    before = len(loopback_guard.allowed)
    assert isinstance(OpenAICompatTranslator(TranslatorConfig()), Translator)
    assert len(loopback_guard.allowed) == before
