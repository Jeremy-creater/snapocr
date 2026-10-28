"""M7 WI-1: the ``[ui] theme`` key (PRD F20-1, F20-2; M7 plan).

Pinned here (beyond the plan text):
- The section sits after ``[notify]`` in the template and in ``KNOWN_KEYS``,
  so a saved theme lands between ``notify.show_text`` and the translator keys.
- A bad value is reported as ``ui.theme`` with the four allowed values and
  falls back to ``system``; nothing else changes.
- ``check`` reports ``BadTheme`` last, after the problems that existed before.
"""

import dataclasses
import tomllib
from pathlib import Path

import pytest

from snapocr.actions.messages import settings_problem_text
from snapocr.config.files import load_config_file
from snapocr.config.load import build_config
from snapocr.config.schema import KNOWN_KEYS, THEMES, AppConfig
from snapocr.config.settings import BadSaveDir, BadTheme, apply, changes, check, settings_of
from snapocr.config.template import DEFAULT_TEMPLATE
from snapocr.config.writer import write_changes

SRC = Path("D:/x/config.local.toml")
DEFAULTS = settings_of(AppConfig())


def uncomment(text):
    return "\n".join(line[2:] if line.startswith("# ") else line for line in text.split("\n"))


def test_themes_and_default():
    assert THEMES == ("system", "light_glass", "dark_glass", "light_solid")
    assert AppConfig().theme == "system"
    assert KNOWN_KEYS["ui"] == ("theme",)
    assert list(KNOWN_KEYS).index("ui") == list(KNOWN_KEYS).index("notify") + 1


@pytest.mark.parametrize("theme", ["system", "light_glass", "dark_glass", "light_solid"])
def test_valid_theme_is_kept(theme):
    cfg, issues = build_config({"ui": {"theme": theme}}, source=SRC)
    assert issues == []
    assert cfg == dataclasses.replace(AppConfig(), theme=theme)


@pytest.mark.parametrize("value", ["dark_solid", "Dark_Glass", "", "classic", 1, True, ["system"]], ids=repr)
def test_bad_theme_is_reported_and_falls_back(value):
    cfg, issues = build_config({"ui": {"theme": value}, "notify": {"show_text": False}}, source=SRC)
    assert [i.key_path for i in issues] == ["ui.theme"]
    reason = issues[0].reason
    assert all(t in reason for t in THEMES)
    assert "using system" in reason
    assert cfg == dataclasses.replace(AppConfig(), show_text=False)


def test_unknown_ui_key_gets_a_suggestion():
    _, issues = build_config({"ui": {"them": "system"}}, source=SRC)
    assert [(i.key_path, "'theme'" in i.reason) for i in issues] == [("ui.them", True)]


def test_template_ui_section_after_notify_with_its_help():
    headers = [line for line in DEFAULT_TEMPLATE.split("\n") if line.startswith("[")]
    assert headers.index("[ui]") == headers.index("[notify]") + 1
    section = DEFAULT_TEMPLATE.split("[ui]\n")[1].split("\n[debug]")[0]
    assert "# theme = \"system\"" in section
    assert all(t in section for t in THEMES)
    assert "毛玻璃" in section
    assert tomllib.loads(uncomment(section)) == {"theme": "system"}


def test_theme_is_a_window_setting():
    assert DEFAULTS.theme == "system"
    assert settings_of(dataclasses.replace(AppConfig(), theme="dark_glass")).theme == "dark_glass"
    assert apply(AppConfig(), dataclasses.replace(DEFAULTS, theme="light_solid")) == dataclasses.replace(
        AppConfig(), theme="light_solid"
    )


def test_changes_theme_sits_between_notify_and_translator():
    new = dataclasses.replace(DEFAULTS, show_text=False, theme="dark_glass", model="qwen3:8b")
    assert list(changes(DEFAULTS, new).items()) == [
        ("notify.show_text", False),
        ("ui.theme", "dark_glass"),
        ("translator.model", "qwen3:8b"),
    ]
    assert changes(DEFAULTS, DEFAULTS) == {}


@pytest.mark.parametrize("value", ["dark_solid", "", None, 3])
def test_check_bad_theme_reported_last(value):
    s = dataclasses.replace(DEFAULTS, save_dir=Path("x"), theme=value)
    assert check(s) == [BadSaveDir(Path("x")), BadTheme(value)]
    with pytest.raises(ValueError):
        apply(AppConfig(), s)


def test_bad_theme_text():
    assert settings_problem_text(BadTheme("x")) == "窗口风格只能是跟随系统、浅色毛玻璃、深色毛玻璃或浅色实底。"


def test_theme_written_into_the_template_and_read_back(tmp_path):
    path = tmp_path / "config.local.toml"
    assert load_config_file(path).created
    write_changes(path, changes(DEFAULTS, dataclasses.replace(DEFAULTS, theme="dark_glass")))
    loaded = load_config_file(path)
    assert loaded.issues == []
    assert loaded.config.theme == "dark_glass"
    section = path.read_text(encoding="utf-8").split("[ui]")[1].split("[debug]")[0]
    assert 'theme = "dark_glass"' in section
    assert '# theme = "system"' not in section  # the commented line was replaced in place
