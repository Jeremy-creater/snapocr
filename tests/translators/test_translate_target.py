"""M6 WI-1 (F19-6): ``translate(text, target)`` overrides the configured direction."""

import json

import pytest

from snapocr.translators.config import TranslatorConfig
from snapocr.translators.openai_compat import OpenAICompatTranslator
from snapocr.translators.types import TranslationResult
from support.fake_openai_server import Reply
from support.tr_strategies import ok

pytestmark = pytest.mark.usefixtures("loopback_guard")


def _translator(fake, **kw):
    fake.reset()
    fake.script(Reply(body=ok("out")))
    return OpenAICompatTranslator(TranslatorConfig(base_url=fake.base_url, timeout_s=2.0, **kw))


def _content(fake):
    return json.loads(fake.requests[0].body)["messages"][0]["content"]


def test_target_zh_overrides_auto_for_chinese_text(fake_server):
    result = _translator(fake_server).translate("今天天气很好", target="zh")
    assert result == TranslationResult("out", "zh", False)
    assert _content(fake_server).startswith("把下面的文本翻译成中文")


def test_target_en_overrides_auto_for_english_text(fake_server):
    result = _translator(fake_server).translate("Hello world", target="en")
    assert result == TranslationResult("out", "en", False)
    assert _content(fake_server).startswith("把下面的文本翻译成英语")


def test_target_overrides_fixed_config(fake_server):
    result = _translator(fake_server, target_lang="en").translate("Hello world", target="zh")
    assert result.target_lang == "zh"
    assert "中文" in _content(fake_server)


@pytest.mark.parametrize(("text", "expected"), [("今天天气很好", "en"), ("Hello world", "zh")])
def test_none_follows_config(fake_server, text, expected):
    assert _translator(fake_server).translate(text, target=None).target_lang == expected


def test_target_sends_text_without_letters(fake_server):
    assert _translator(fake_server).translate("123", target="en") == TranslationResult("out", "en", False)
    assert len(fake_server.requests) == 1


def test_blank_text_still_skipped_with_target(fake_server):
    assert _translator(fake_server).translate("  ", target="zh") == TranslationResult("", None, True)
    assert fake_server.requests == []


@pytest.mark.parametrize("bad", ["auto", "ZH", "fr", "", 1])
def test_bad_target_rejected(fake_server, bad):
    with pytest.raises(ValueError, match="target"):
        _translator(fake_server).translate("Hello", target=bad)
    assert fake_server.requests == []
