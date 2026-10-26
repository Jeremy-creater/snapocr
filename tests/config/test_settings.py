"""M3 WI-1: the settings-window values and their checks (PRD F11-1, F11-3; M3 plan D4).

Pinned here (beyond the plan text):
- ``check`` reports each pair of commands sharing a hotkey once, in command
  order (first, second), then a bad model, then a bad target language.
- ``changes`` gives "section.key" -> TOML value for the differing items only,
  in ``KNOWN_KEYS`` order; hotkeys as their canonical text. A hotkey missing
  from the new settings (it was disabled) yields no change.
- ``apply`` replaces only the window's items; it raises ValueError when
  ``check`` would report a problem.
"""

import dataclasses
from pathlib import Path
from types import MappingProxyType

import pytest
from hypothesis import given
from hypothesis import strategies as st

from snapocr.commands import Command
from snapocr.config.load import build_config
from snapocr.config.schema import DEFAULT_HOTKEYS, HOTKEY_COMMANDS, KNOWN_KEYS, AppConfig
from snapocr.config.settings import (
    BadModel,
    BadTargetLang,
    DuplicateHotkey,
    Settings,
    apply,
    changes,
    check,
    settings_of,
)
from snapocr.engines.config import OcrEngineConfig
from snapocr.hotkeys import Hotkey, parse_hotkey
from snapocr.postprocess import PostprocessOptions, Replacements
from snapocr.translators.config import TranslatorConfig

DEFAULTS = settings_of(AppConfig())


def with_hotkeys(s: Settings, **texts: str) -> Settings:
    hotkeys = dict(s.hotkeys)
    for name, text in texts.items():
        hotkeys[Command(name)] = parse_hotkey(text)
    return dataclasses.replace(s, hotkeys=MappingProxyType(hotkeys))


def test_settings_of_defaults():
    assert DEFAULTS == Settings(
        hotkeys=DEFAULT_HOTKEYS,
        paragraphs=True,
        spacing=True,
        punctuation=True,
        target_lang="auto",
        model="hy-mt2:7b",
    )


def test_settings_of_custom_config():
    config = AppConfig(
        hotkeys=MappingProxyType({Command.OCR: parse_hotkey("Ctrl+Q")}),
        postprocess=PostprocessOptions(paragraphs=False, spacing=True, punctuation=False),
        translator=TranslatorConfig(model="qwen3:8b", target_lang="en"),
    )
    s = settings_of(config)
    assert dict(s.hotkeys) == {Command.OCR: parse_hotkey("Ctrl+Q")}
    assert (s.paragraphs, s.spacing, s.punctuation) == (False, True, False)
    assert (s.target_lang, s.model) == ("en", "qwen3:8b")


def test_settings_hotkeys_are_read_only():
    s = with_hotkeys(DEFAULTS, capture="Ctrl+Q")
    with pytest.raises(TypeError):
        s.hotkeys[Command.OCR] = parse_hotkey("Ctrl+W")


def test_check_defaults_is_clean():
    assert check(DEFAULTS) == []


def test_check_duplicate_pairs_in_command_order():
    s = with_hotkeys(DEFAULTS, capture="Ctrl+Q", translate="Ctrl+Q", last_result="Ctrl+Q", ocr="Ctrl+W")
    q = parse_hotkey("Ctrl+Q")
    assert check(s) == [
        DuplicateHotkey(Command.CAPTURE, Command.TRANSLATE, q),
        DuplicateHotkey(Command.CAPTURE, Command.LAST_RESULT, q),
        DuplicateHotkey(Command.TRANSLATE, Command.LAST_RESULT, q),
    ]


@pytest.mark.parametrize("model", ["", " qwen3:8b", "qwen3:8b ", "gpt-oss:120b-cloud", "kimi:cloud", "a\x07b"])
def test_check_bad_model(model):
    problems = check(dataclasses.replace(DEFAULTS, model=model))
    assert len(problems) == 1
    assert isinstance(problems[0], BadModel)
    assert problems[0].reason  # TranslatorConfig's own reason, without the "model: " prefix
    assert not problems[0].reason.startswith("model")


@pytest.mark.parametrize("lang", ["", "fr", "AUTO", None])
def test_check_bad_target_lang(lang):
    assert check(dataclasses.replace(DEFAULTS, target_lang=lang)) == [BadTargetLang(lang)]


def test_check_reports_all_kinds_in_order():
    s = dataclasses.replace(with_hotkeys(DEFAULTS, ocr="Alt+1"), model="", target_lang="fr")
    kinds = [type(p) for p in check(s)]
    assert kinds == [DuplicateHotkey, BadModel, BadTargetLang]


def test_changes_none_for_same():
    assert changes(DEFAULTS, DEFAULTS) == {}


def test_changes_values_and_order():
    new = dataclasses.replace(
        with_hotkeys(DEFAULTS, translate="ctrl+shift+t", capture="Win+F1"),
        punctuation=False,
        spacing=False,
        model="qwen3:8b",
        target_lang="zh",
    )
    got = changes(DEFAULTS, new)
    assert got == {
        "hotkeys.capture": "Win+F1",
        "hotkeys.translate": "Ctrl+Shift+T",
        "postprocess.spacing": False,
        "postprocess.punctuation": False,
        "translator.model": "qwen3:8b",
        "translator.target_lang": "zh",
    }
    assert list(got) == [
        "hotkeys.capture",
        "hotkeys.translate",
        "postprocess.spacing",
        "postprocess.punctuation",
        "translator.model",
        "translator.target_lang",
    ]


def test_changes_hotkey_newly_set_and_disabled_left_alone():
    old = dataclasses.replace(DEFAULTS, hotkeys=MappingProxyType({Command.CAPTURE: parse_hotkey("Alt+1")}))
    new = dataclasses.replace(DEFAULTS, hotkeys=MappingProxyType({Command.OCR: parse_hotkey("Alt+2")}))
    assert changes(old, new) == {"hotkeys.ocr": "Alt+2"}


def test_apply_keeps_everything_else():
    config = AppConfig(
        ocr=OcrEngineConfig(min_score=0.7, model_dir=Path("D:/models")),
        replacements=Replacements.from_mapping({"0CR": "OCR"}),
        translator=TranslatorConfig(timeout_s=12, prompt_template="T {source_text}", base_url="http://127.0.0.1:1234"),
    )
    new = dataclasses.replace(
        with_hotkeys(settings_of(config), ocr="Ctrl+Q"), paragraphs=False, model="qwen3:8b", target_lang="en"
    )
    out = apply(config, new)
    assert settings_of(out) == new
    assert out.ocr == config.ocr
    assert out.replacements == config.replacements
    assert out.translator == dataclasses.replace(config.translator, model="qwen3:8b", target_lang="en")
    assert out.postprocess == PostprocessOptions(paragraphs=False)


def test_apply_rejects_problems():
    with pytest.raises(ValueError):
        apply(AppConfig(), with_hotkeys(DEFAULTS, ocr="Alt+1"))
    with pytest.raises(ValueError):
        apply(AppConfig(), dataclasses.replace(DEFAULTS, model="x:cloud"))


# --- properties ---------------------------------------------------------------------

_KEYS = [0x41 + n for n in range(26)] + [0x30 + n for n in range(10)] + [0x70 + n for n in range(24)]
_hotkey = st.builds(Hotkey, st.integers(1, 0xF), st.sampled_from(_KEYS))


@st.composite
def settings(draw):
    keys = draw(st.lists(_hotkey, min_size=4, max_size=4, unique=True))
    return Settings(
        hotkeys=MappingProxyType(dict(zip(HOTKEY_COMMANDS, keys, strict=True))),
        paragraphs=draw(st.booleans()),
        spacing=draw(st.booleans()),
        punctuation=draw(st.booleans()),
        target_lang=draw(st.sampled_from(["auto", "zh", "en"])),
        model=draw(st.sampled_from(["hy-mt2:7b", "qwen3:8b", "llama3", "my/model:q4_K_M"])),
    )


@given(settings())
def test_changes_of_self_is_empty(s):
    assert changes(s, s) == {}


def _nest(flat):
    data: dict = {}
    for dotted, value in flat.items():
        section, key = dotted.split(".")
        data.setdefault(section, {})[key] = value
    return data


@given(settings(), settings())
def test_changes_roundtrip_through_loader(old, new):
    """Old values written as a full file, then the changes on top, load back as ``new``."""
    data = _nest(changes(DEFAULTS, old))
    for dotted, value in changes(old, new).items():
        section, key = dotted.split(".")
        data.setdefault(section, {})[key] = value
    config, issues = build_config(data, source=Path("config.local.toml"))
    assert issues == []
    assert settings_of(config) == new


@given(settings())
def test_changes_keys_are_known(s):
    for dotted in changes(DEFAULTS, s):
        section, key = dotted.split(".")
        assert key in KNOWN_KEYS[section]


@given(settings())
def test_apply_then_settings_of(s):
    assert settings_of(apply(AppConfig(), s)) == s
