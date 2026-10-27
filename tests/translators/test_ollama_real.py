"""WI-8: real Ollama ``hy-mt2:7b`` (integration lane, manual).

Run: ``python -m pytest -m "integration and not perf"``. Requires Ollama on
127.0.0.1:11434 with hy-mt2:7b imported; ``require_ollama`` FAILS (never skips)
otherwise. Sampling is pinned to temperature 0 / seed 42; assertions are about
direction and keywords only, because even then output is not guaranteed stable (R7).
"""

import dataclasses
import json
import logging
from pathlib import Path

import pytest

from snapocr.translators import OpenAICompatTranslator, TranslationError, TranslationErrorKind
from snapocr.translators.config import TranslatorConfig
from snapocr.translators.direction import count_scripts, detect_target_lang
from snapocr.translators.errors import ErrorContext
from snapocr.translators.http_transport import post_json
from snapocr.translators.protocol import build_chat_request, parse_chat_response

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("require_ollama", "loopback_guard")]

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "translators"
REAL = TranslatorConfig(sampling={"temperature": 0, "seed": 42})


def _translate(text, config=REAL):
    return OpenAICompatTranslator(config).translate(text)


def _assert_clean(text):
    assert text
    assert text == text.strip()
    assert "<think>" not in text and "</think>" not in text


def test_real_zh_to_en():
    result = _translate("今天天气很好，我们去公园散步。")
    assert result.target_lang == "en"
    assert result.skipped is False
    _assert_clean(result.text)
    assert detect_target_lang(result.text, 0.3) == "zh"
    assert "park" in result.text.lower()


def test_real_en_to_zh():
    result = _translate("The quick brown fox jumps over the lazy dog.")
    assert result.target_lang == "zh"
    _assert_clean(result.text)
    assert detect_target_lang(result.text, 0.3) == "en"
    assert count_scripts(result.text)[0] > 0


def test_real_model_not_found():
    config = dataclasses.replace(REAL, model="snapocr-no-such-model:0")
    with pytest.raises(TranslationError) as info:
        _translate("你好", config)
    err = info.value
    assert err.kind is TranslationErrorKind.MODEL_NOT_FOUND
    assert err.status == 404
    assert "snapocr-no-such-model:0" in str(err)
    assert REAL.endpoint.url in str(err)


def test_real_response_shape_contract():
    ctx = ErrorContext(REAL.endpoint.url, REAL.model)
    status, body = post_json(
        REAL.endpoint, build_chat_request(REAL, "en", "你好"), 60, ctx=ctx
    )
    assert status == 200
    real = json.loads(body)
    fixture = json.loads((FIXTURES / "chat_ok.json").read_bytes())
    assert set(real) >= set(fixture), sorted(real)
    assert set(real["choices"][0]) >= set(fixture["choices"][0])
    assert set(real["choices"][0]["message"]) >= set(fixture["choices"][0]["message"])
    assert real["choices"][0]["finish_reason"] == "stop"
    assert parse_chat_response(200, body, ctx=ctx)


def test_real_truncated_by_max_tokens():
    config = dataclasses.replace(REAL, sampling={"temperature": 0, "seed": 42, "max_tokens": 4})
    text = (FIXTURES / "perf_zh_200.txt").read_text(encoding="utf-8").strip()
    with pytest.raises(TranslationError) as info:
        _translate(text, config)
    assert info.value.kind is TranslationErrorKind.TRUNCATED


def test_real_no_text_in_logs(caplog, capfd):
    caplog.set_level(logging.DEBUG, logger="snapocr.translators")
    source = "早上好，今天开会。"
    result = _translate(source)
    out, err = capfd.readouterr()
    for secret in (source, result.text):
        assert secret not in out and secret not in err
        for record in caplog.records:
            assert secret not in record.getMessage()
            assert secret not in repr(vars(record))
    assert any(r.levelno == logging.DEBUG for r in caplog.records)


def test_real_loopback_only(loopback_guard):
    # Kept last in the module; the fixture's teardown checks again.
    assert loopback_guard.blocked == []
    assert loopback_guard.allowed
    for _kind, target in loopback_guard.allowed:
        host = target[0] if isinstance(target, tuple) else target
        assert host == "127.0.0.1"


def test_real_model_list_has_the_default_model():
    # M3 WI-10 (F11-7): Ollama's OpenAI-compatible /v1/models lists imported models.
    from snapocr.translators.openai_compat import list_models

    models = list_models(TranslatorConfig())
    assert "hy-mt2:7b" in models
    assert list(models) == sorted(set(models))
