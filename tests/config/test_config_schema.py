"""M2 WI-6: building AppConfig from parsed TOML (PRD F9-3, F5-2, F2-6; M2 plan D9).

Rules pinned here (beyond the plan text):
- A hotkey that is invalid, or duplicates an earlier one (in Command order),
  gets one issue and falls back to its default; if that default is taken too,
  a second issue says it is disabled (left out of ``hotkeys``).
- A section that is not a table: one issue, the whole section uses defaults.
- An invalid replacement table: one issue on ``postprocess.replacements``, the
  table becomes empty.
- A translator field that ``TranslatorConfig`` rejects: one issue on
  ``translator.<field>``, that field uses its default.
"""

import dataclasses
import datetime
from pathlib import Path
from types import MappingProxyType

import pytest
from hypothesis import given
from hypothesis import strategies as st

from snapocr.commands import Command
from snapocr.config.load import build_config
from snapocr.config.schema import KNOWN_KEYS, AppConfig, ConfigIssue
from snapocr.engines.config import OcrEngineConfig
from snapocr.hotkeys import MOD_ALT, MOD_CONTROL, Hotkey, parse_hotkey
from snapocr.postprocess import PostprocessOptions, Replacements
from snapocr.translators.config import TranslatorConfig

SRC = Path("D:/cfg/config.local.toml")
C = Command
DEFAULT_HK = {
    C.CAPTURE: Hotkey(MOD_ALT, 0x31),
    C.OCR: Hotkey(MOD_ALT, 0x32),
    C.TRANSLATE: Hotkey(MOD_ALT, 0x33),
    C.LAST_RESULT: Hotkey(MOD_ALT, 0x34),
    C.CODE_OCR: Hotkey(MOD_ALT, 0x35),  # M3 WI-14 (F13-1)
    C.TABLE_OCR: Hotkey(MOD_ALT, 0x36),  # M4 WI-15 (F16-1)
}


def build(data):
    return build_config(data, source=SRC)


def paths(issues):
    return [i.key_path for i in issues]


def only_issue(issues, key_path):
    assert paths(issues) == [key_path], [str(i) for i in issues]
    return issues[0]


# --- defaults --------------------------------------------------------------------


def test_empty_is_all_defaults():
    cfg, issues = build({})
    assert issues == []
    assert cfg == AppConfig()
    assert dict(cfg.hotkeys) == DEFAULT_HK
    assert cfg.ocr == OcrEngineConfig()
    assert cfg.postprocess == PostprocessOptions()
    assert cfg.replacements == Replacements.EMPTY
    assert cfg.translator == TranslatorConfig()


def test_known_keys():
    assert dict(KNOWN_KEYS) == {
        "hotkeys": ("capture", "ocr", "translate", "last_result", "code_ocr", "table_ocr"),  # M3 WI-14, M4 WI-15
        "ocr": ("min_score", "model_dir"),
        "postprocess": ("paragraphs", "spacing", "punctuation", "replacements"),
        "notify": ("show_text",),  # M3 WI-11 (F7-2, F11-8)
        "debug": ("enabled",),  # M3 WI-12 (F12)
        "translator": ("base_url", "model", "timeout_s", "target_lang", "direction_threshold",
                       "prompt_template", "max_input_chars", "sampling"),
    }


def test_issue_str():
    assert str(ConfigIssue(SRC, "translator.timeout_s", "must be a number")) == (
        "config.local.toml: translator.timeout_s: must be a number"
    )
    assert str(ConfigIssue(SRC, "", "TOML syntax error")) == "config.local.toml: TOML syntax error"


# --- examples --------------------------------------------------------------------


def test_full_valid_config():
    data = {
        "hotkeys": {"capture": "Ctrl+Alt+1", "ocr": "ctrl + alt + 2", "translate": "Win+T", "last_result": "Alt+F4"},
        "ocr": {"min_score": 0.7, "model_dir": "models"},
        "postprocess": {"paragraphs": False, "spacing": True, "punctuation": False,
                        "replacements": {"0CR": "OCR"}},
        "translator": {"base_url": "http://127.0.0.1:8080", "model": "qwen3:8b", "timeout_s": 30,
                       "target_lang": "en", "direction_threshold": 0.5,
                       "prompt_template": "Translate to {target_language}:\n{source_text}",
                       "max_input_chars": 2000, "sampling": {"temperature": 0.2, "stop": ["\n\n"]}},
    }
    cfg, issues = build(data)
    assert issues == []
    assert dict(cfg.hotkeys) == {
        C.CAPTURE: Hotkey(MOD_CONTROL | MOD_ALT, 0x31),
        C.OCR: Hotkey(MOD_CONTROL | MOD_ALT, 0x32),
        C.TRANSLATE: Hotkey(0x8, 0x54),
        C.LAST_RESULT: Hotkey(MOD_ALT, 0x73),
        C.CODE_OCR: DEFAULT_HK[C.CODE_OCR],  # not in the file: default (M3 WI-14)
        C.TABLE_OCR: DEFAULT_HK[C.TABLE_OCR],  # not in the file: default (M4 WI-15)
    }
    assert cfg.ocr == OcrEngineConfig(min_score=0.7, model_dir=Path("D:/cfg/models"))
    assert cfg.postprocess == PostprocessOptions(paragraphs=False, spacing=True, punctuation=False)
    assert cfg.replacements == Replacements.from_mapping({"0CR": "OCR"})
    assert cfg.translator == TranslatorConfig(
        base_url="http://127.0.0.1:8080", model="qwen3:8b", timeout_s=30.0, target_lang="en",
        direction_threshold=0.5, prompt_template="Translate to {target_language}:\n{source_text}",
        max_input_chars=2000, sampling={"temperature": 0.2, "stop": ("\n\n",)},
    )


def test_model_dir_absolute_kept():
    cfg, issues = build({"ocr": {"model_dir": "E:/models/rapid"}})
    assert issues == []
    assert cfg.ocr.model_dir == Path("E:/models/rapid")


def test_min_score_int_accepted():
    cfg, issues = build({"ocr": {"min_score": 1}})
    assert issues == []
    assert cfg.ocr.min_score == 1.0


def test_unknown_translator_key_suggests():
    cfg, issues = build({"translator": {"timout_s": 30}})
    issue = only_issue(issues, "translator.timout_s")
    assert "timeout_s" in issue.reason
    assert issue.file == SRC
    assert cfg == AppConfig()


def test_unknown_key_without_suggestion():
    cfg, issues = build({"ocr": {"zzzzzz": 1}})
    issue = only_issue(issues, "ocr.zzzzzz")
    assert "did you mean" not in issue.reason
    assert cfg == AppConfig()


def test_unknown_section_suggests():
    cfg, issues = build({"hotkey": {"ocr": "Alt+9"}})
    issue = only_issue(issues, "hotkey")
    assert "hotkeys" in issue.reason
    assert cfg == AppConfig()


def test_bad_hotkey_names_key_and_token():
    cfg, issues = build({"hotkeys": {"ocr": "Alt+Foo"}})
    issue = only_issue(issues, "hotkeys.ocr")
    assert "Foo" in issue.reason
    assert dict(cfg.hotkeys) == DEFAULT_HK


@pytest.mark.parametrize("value", [5, True, ["Alt", "2"], "", {"a": 1}])
def test_hotkey_not_a_valid_string(value):
    cfg, issues = build({"hotkeys": {"ocr": value}})
    only_issue(issues, "hotkeys.ocr")
    assert dict(cfg.hotkeys) == DEFAULT_HK


def test_duplicate_hotkey_second_falls_back():
    cfg, issues = build({"hotkeys": {"capture": "Ctrl+Q", "translate": "ctrl+q"}})
    issue = only_issue(issues, "hotkeys.translate")
    assert "hotkeys.capture" in issue.reason
    assert dict(cfg.hotkeys) == {**DEFAULT_HK, C.CAPTURE: Hotkey(MOD_CONTROL, 0x51)}


def test_duplicate_order_is_command_order_not_file_order():
    cfg, issues = build({"hotkeys": {"translate": "Ctrl+Q", "capture": "Ctrl+Q"}})
    only_issue(issues, "hotkeys.translate")
    assert cfg.hotkeys[C.CAPTURE] == Hotkey(MOD_CONTROL, 0x51)
    assert cfg.hotkeys[C.TRANSLATE] == DEFAULT_HK[C.TRANSLATE]


def test_duplicate_whose_default_is_taken_is_disabled():
    # capture takes Alt+2, ocr duplicates it, and ocr's default Alt+2 is taken too.
    cfg, issues = build({"hotkeys": {"capture": "Alt+2", "ocr": "Alt+2"}})
    assert paths(issues) == ["hotkeys.ocr", "hotkeys.ocr"]
    assert "hotkeys.capture" in issues[0].reason and "disabled" in issues[1].reason
    assert dict(cfg.hotkeys) == {C.CAPTURE: Hotkey(MOD_ALT, 0x32), C.TRANSLATE: DEFAULT_HK[C.TRANSLATE],
                                 C.LAST_RESULT: DEFAULT_HK[C.LAST_RESULT], C.CODE_OCR: DEFAULT_HK[C.CODE_OCR],
                                 C.TABLE_OCR: DEFAULT_HK[C.TABLE_OCR]}


def test_invalid_hotkey_whose_default_is_taken_is_disabled():
    cfg, issues = build({"hotkeys": {"capture": "Alt+3", "translate": "Alt+Foo"}})
    assert paths(issues) == ["hotkeys.translate", "hotkeys.translate"]
    assert "Foo" in issues[0].reason and "disabled" in issues[1].reason
    assert C.TRANSLATE not in cfg.hotkeys
    assert cfg.hotkeys[C.CAPTURE] == Hotkey(MOD_ALT, 0x33)


@pytest.mark.parametrize(
    ("data", "key_path"),
    [
        ({"ocr": {"min_score": True}}, "ocr.min_score"),
        ({"ocr": {"min_score": 1.5}}, "ocr.min_score"),
        ({"ocr": {"min_score": -0.1}}, "ocr.min_score"),
        ({"ocr": {"min_score": float("nan")}}, "ocr.min_score"),
        ({"ocr": {"min_score": 10**400}}, "ocr.min_score"),
        ({"ocr": {"min_score": "0.5"}}, "ocr.min_score"),
        ({"ocr": {"model_dir": 5}}, "ocr.model_dir"),
        ({"ocr": {"model_dir": ""}}, "ocr.model_dir"),
        ({"ocr": {"model_dir": "  "}}, "ocr.model_dir"),
        ({"postprocess": {"paragraphs": 1}}, "postprocess.paragraphs"),
        ({"postprocess": {"spacing": "yes"}}, "postprocess.spacing"),
        ({"postprocess": {"punctuation": None}}, "postprocess.punctuation"),
        ({"postprocess": {"replacements": {"xy": "q", "qz": "w"}}}, "postprocess.replacements"),
        ({"postprocess": {"replacements": {"a": ""}}}, "postprocess.replacements"),
        ({"postprocess": {"replacements": ["0CR", "OCR"]}}, "postprocess.replacements"),
        ({"postprocess": {"replacements": {"0CR": 1}}}, "postprocess.replacements"),
        ({"translator": {"base_url": "http://localhost:11434"}}, "translator.base_url"),
        ({"translator": {"model": "glm-4.6:cloud"}}, "translator.model"),
        ({"translator": {"timeout_s": 0}}, "translator.timeout_s"),
        ({"translator": {"timeout_s": 10**400}}, "translator.timeout_s"),
        ({"translator": {"target_lang": "fr"}}, "translator.target_lang"),
        ({"translator": {"direction_threshold": 0}}, "translator.direction_threshold"),
        ({"translator": {"prompt_template": "no placeholder"}}, "translator.prompt_template"),
        ({"translator": {"max_input_chars": 0}}, "translator.max_input_chars"),
        ({"translator": {"sampling": {"foo": 1}}}, "translator.sampling"),
        ({"translator": {"sampling": 5}}, "translator.sampling"),
        ({"hotkeys": 5}, "hotkeys"),
        ({"ocr": "fast"}, "ocr"),
        ({"postprocess": [1, 2]}, "postprocess"),
        ({"translator": True}, "translator"),
    ],
)
def test_bad_value_falls_back_to_default(data, key_path):
    cfg, issues = build(data)
    issue = only_issue(issues, key_path)
    assert issue.reason
    assert issue.file == SRC
    assert cfg == AppConfig()


def test_translator_reason_not_doubled():
    _, issues = build({"translator": {"timeout_s": 0}})
    assert not issues[0].reason.startswith("timeout_s:")


def test_one_bad_translator_key_keeps_the_rest():
    cfg, issues = build({"translator": {"model": "glm-4.6:cloud", "timeout_s": 30, "base_url": "http://x"}})
    assert sorted(paths(issues)) == ["translator.base_url", "translator.model"]
    assert cfg.translator == TranslatorConfig(timeout_s=30.0)


def test_bad_replacements_reason_names_key():
    _, issues = build({"postprocess": {"replacements": {"xy": "q", "qz": "w"}}})
    assert "'xy'" in issues[0].reason


@pytest.mark.parametrize("data", [None, 5, "x", [1]])
def test_top_level_not_a_table(data):
    cfg, issues = build(data)
    only_issue(issues, "")
    assert cfg == AppConfig()


def test_several_problems_all_reported():
    cfg, issues = build({
        "hotkeys": {"ocr": "Alt+Foo"},
        "ocr": {"min_score": 2},
        "translator": {"timout_s": 3, "model": "x:cloud"},
        "extra": {},
    })
    assert sorted(paths(issues)) == ["extra", "hotkeys.ocr", "ocr.min_score", "translator.model",
                                     "translator.timout_s"]
    assert cfg == AppConfig()


# --- properties ------------------------------------------------------------------

scalars = (st.booleans() | st.integers() | st.floats() | st.text(max_size=8)
           | st.datetimes() | st.dates() | st.times())
toml_values = st.recursive(
    scalars,
    lambda inner: st.lists(inner, max_size=3) | st.dictionaries(st.text(max_size=6), inner, max_size=3),
    max_leaves=10,
)
ALL_KEYS = sorted({k for ks in KNOWN_KEYS.values() for k in ks})


@st.composite
def toml_shaped(draw):
    data = {}
    for name in draw(st.lists(st.sampled_from([*KNOWN_KEYS, "extra", "hotkey"]), unique=True)):
        if draw(st.booleans()):
            keys = st.sampled_from([*ALL_KEYS, "timout_s", "x"]) | st.text(max_size=5)
            data[name] = draw(st.dictionaries(keys, toml_values, max_size=5))
        else:
            data[name] = draw(toml_values)
    return data


@given(toml_shaped() | toml_values)
def test_total(data):
    cfg, issues = build(data)
    assert isinstance(cfg, AppConfig)
    assert all(isinstance(i, ConfigIssue) and i.file == SRC and i.reason for i in issues)
    # Enabled hotkeys never collide.
    assert len(set(cfg.hotkeys.values())) == len(cfg.hotkeys)


# Valid values; hotkeys avoid Alt+1..4 so a key's fallback never collides.
HK_POOL = ["Ctrl+Alt+Q", "Ctrl+Shift+F5", "Win+X", "Alt+F12", "Ctrl+9", "Shift+Insert"]


@st.composite
def valid_configs(draw):
    hk_texts = draw(st.permutations(HK_POOL))
    hk_keys = draw(st.lists(st.sampled_from(KNOWN_KEYS["hotkeys"]), unique=True))
    data = {
        "hotkeys": {k: hk_texts[i] for i, k in enumerate(hk_keys)},
        "ocr": {"min_score": draw(st.floats(0, 1)), "model_dir": draw(st.sampled_from(["m", "a/b", "E:/x"]))},
        "postprocess": {
            "paragraphs": draw(st.booleans()), "spacing": draw(st.booleans()),
            "punctuation": draw(st.booleans()),
            "replacements": draw(st.sampled_from([{}, {"0CR": "OCR"}, {"l0": "10", "rn": "m"}])),
        },
        "translator": {
            "base_url": f"http://127.0.0.1:{draw(st.integers(1, 65535))}",
            "model": draw(st.sampled_from(["hy-mt2:7b", "qwen3:8b", "gemma"])),
            "timeout_s": draw(st.integers(1, 600) | st.floats(0.5, 600)),
            "target_lang": draw(st.sampled_from(["auto", "zh", "en"])),
            "direction_threshold": draw(st.floats(0.01, 1)),
            "prompt_template": draw(st.sampled_from(["{source_text}", "to {target_language}: {source_text}"])),
            "max_input_chars": draw(st.integers(1, 100000)),
            "sampling": draw(st.sampled_from([{}, {"temperature": 0.1}, {"top_p": 1.0, "seed": 7}])),
        },
    }
    return data


def expected_for(data):
    """Oracle: the AppConfig a valid ``data`` must produce, built from the constructors."""
    hk = dict(DEFAULT_HK)
    for k, text in data["hotkeys"].items():
        hk[Command(k)] = parse_hotkey(text)
    o, p, t = data["ocr"], data["postprocess"], data["translator"]
    return AppConfig(
        hotkeys=MappingProxyType(hk),
        ocr=OcrEngineConfig(min_score=float(o["min_score"]), model_dir=SRC.parent / o["model_dir"]),
        postprocess=PostprocessOptions(p["paragraphs"], p["spacing"], p["punctuation"]),
        replacements=Replacements.from_mapping(p["replacements"]),
        translator=TranslatorConfig(**t),
    )


@given(valid_configs())
def test_valid_config_no_issues_and_faithful(data):
    cfg, issues = build(data)
    assert issues == []
    assert cfg == expected_for(data)


BAD_VALUES = [
    ("hotkeys", "capture", "Alt+Foo"), ("hotkeys", "last_result", 7),
    ("ocr", "min_score", True), ("ocr", "model_dir", ""),
    ("postprocess", "spacing", "no"), ("postprocess", "replacements", {"ab": "abc"}),
    ("translator", "base_url", "http://10.0.0.1:1"), ("translator", "model", "a:b-cloud"),
    ("translator", "timeout_s", -1), ("translator", "target_lang", "de"),
    ("translator", "direction_threshold", 2), ("translator", "prompt_template", 3),
    ("translator", "max_input_chars", 1.5), ("translator", "sampling", {"top_k": 3}),
]


def reset(expected, section, key):
    """``expected`` with one key back at its default."""
    if section == "hotkeys":
        hk = dict(expected.hotkeys)
        hk[Command(key)] = DEFAULT_HK[Command(key)]
        return dataclasses.replace(expected, hotkeys=MappingProxyType(hk))
    if section == "ocr":
        default = getattr(OcrEngineConfig(), key)
        return dataclasses.replace(expected, ocr=dataclasses.replace(expected.ocr, **{key: default}))
    if section == "postprocess":
        if key == "replacements":
            return dataclasses.replace(expected, replacements=Replacements.EMPTY)
        default = getattr(PostprocessOptions(), key)
        return dataclasses.replace(expected, postprocess=dataclasses.replace(expected.postprocess, **{key: default}))
    t = expected.translator
    kw = {f.name: getattr(t, f.name) for f in dataclasses.fields(t) if f.init and f.name != key}
    return dataclasses.replace(expected, translator=TranslatorConfig(**kw))


@given(valid_configs(), st.sampled_from(BAD_VALUES))
def test_locality_one_bad_key(data, bad):
    section, key, value = bad
    good, _ = build(data)
    data[section] = {**data[section], key: value}
    cfg, issues = build(data)
    assert paths(issues) == [f"{section}.{key}"]
    assert cfg == reset(good, section, key)


@given(valid_configs(), st.sampled_from(["translator.timout_s", "ocr.minscore", "hotkeys.capturee"]))
def test_locality_unknown_key(data, dotted):
    section, key = dotted.split(".")
    good, _ = build(data)
    data[section] = {**data[section], key: 1}
    cfg, issues = build(data)
    assert paths(issues) == [dotted]
    assert cfg == good


def test_datetime_value_reported_not_crashing():
    cfg, issues = build({"translator": {"timeout_s": datetime.time(1, 2)}})
    only_issue(issues, "translator.timeout_s")
    assert cfg == AppConfig()


# --- M3 WI-11: [notify] show_text (F7-2, F11-8) ---------------------------------------


def test_notify_show_text_defaults_to_true():
    assert AppConfig().show_text is True
    cfg, issues = build({"notify": {}})
    assert issues == [] and cfg.show_text is True


def test_notify_show_text_false():
    cfg, issues = build({"notify": {"show_text": False}})
    assert issues == []
    assert cfg == dataclasses.replace(AppConfig(), show_text=False)


@pytest.mark.parametrize("value", ["no", 0, 1, "true"])
def test_notify_show_text_bad_value_falls_back(value):
    cfg, issues = build({"notify": {"show_text": value}})
    issue = only_issue(issues, "notify.show_text")
    assert issue.reason == f"must be true or false, got {value!r}; using true"
    assert cfg.show_text is True


def test_notify_unknown_key_suggests():
    cfg, issues = build({"notify": {"show_txt": False}})
    issue = only_issue(issues, "notify.show_txt")
    assert "show_text" in issue.reason
    assert cfg.show_text is True


def test_notify_not_a_table():
    cfg, issues = build({"notify": True})
    only_issue(issues, "notify")
    assert cfg.show_text is True


# --- M3 WI-12: [debug] enabled (F12) -----------------------------------------------------


def test_debug_defaults_to_off():
    assert AppConfig().debug is False
    cfg, issues = build({"debug": {}})
    assert issues == [] and cfg.debug is False


def test_debug_enabled():
    cfg, issues = build({"debug": {"enabled": True}})
    assert issues == []
    assert cfg == dataclasses.replace(AppConfig(), debug=True)


def test_debug_bad_value_falls_back():
    cfg, issues = build({"debug": {"enabled": "yes"}})
    issue = only_issue(issues, "debug.enabled")
    assert issue.reason == "must be true or false, got 'yes'; using false"
    assert cfg.debug is False


def test_debug_is_not_a_window_setting():
    from snapocr.config.settings import apply, settings_of

    config = dataclasses.replace(AppConfig(), debug=True)
    assert apply(config, settings_of(config)).debug is True
