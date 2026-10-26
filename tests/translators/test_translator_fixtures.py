"""F4 WI-5: format of the hand-written translator fixtures (matrix test_translator_fixtures_format)."""

import json
from pathlib import Path

import pytest

from snapocr.translators.direction import detect_target_lang

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "translators"
JSON_NAMES = ["chat_ok.json", "chat_think.json", "chat_length.json", "error_model_not_found.json"]
ALL_NAMES = [*JSON_NAMES, "perf_zh_200.txt"]


def _read(name: str) -> bytes:
    path = FIXTURES / name
    if not path.is_file():
        pytest.fail(f"missing translator fixture {path}")
    return path.read_bytes()


@pytest.mark.parametrize("name", ALL_NAMES)
def test_fixture_encoding(name):
    raw = _read(name)
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert b"\r" not in raw
    text = raw.decode("utf-8")
    assert "ZQXJ" not in text


@pytest.mark.parametrize("name", JSON_NAMES)
def test_fixture_json_parses(name):
    assert isinstance(json.loads(_read(name)), dict)


def test_chat_fixture_shapes():
    ok = json.loads(_read("chat_ok.json"))
    assert isinstance(ok["choices"][0]["message"]["content"], str)
    assert ok["choices"][0]["finish_reason"] == "stop"
    assert json.loads(_read("chat_length.json"))["choices"][0]["finish_reason"] == "length"


def test_perf_text_shape():
    text = _read("perf_zh_200.txt").decode("utf-8").strip()
    assert 150 <= len(text) <= 200
    assert detect_target_lang(text, 0.3) == "en"
