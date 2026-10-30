"""M9 WI-5: the config file by platform (PRD F23-2, F9-2, F9-3, F11-4; M9 plan D9).

Pinned here (beyond the plan text):
- ``template(platform)``; ``DEFAULT_TEMPLATE`` is ``template("win32")``. The
  Mac template explains Option and Cmd and never mentions Windows: the hotkey
  help, the theme help (follows the system, solid only on a Mac), the save
  folder help and the model folder example are Mac ones.
- ``build_config``, ``load_config_file``, ``settings.changes`` and
  ``write_changes`` take ``platform`` (keyword, default ``"win32"``).
"""

import dataclasses
import tomllib

import pytest

from snapocr.commands import Command
from snapocr.config.files import load_config_file
from snapocr.config.load import build_config
from snapocr.config.schema import DEFAULT_HOTKEYS, KNOWN_KEYS, AppConfig
from snapocr.config.settings import changes, settings_of
from snapocr.config.template import DEFAULT_TEMPLATE, template
from snapocr.config.writer import write_changes
from snapocr.engines.config import OcrEngineConfig
from snapocr.hotkeys import MOD_ALT, MOD_CMD, MOD_SHIFT, Hotkey
from snapocr.postprocess import Replacements


def uncomment(text: str) -> str:
    return "\n".join(line[2:] if line.startswith("# ") else line for line in text.split("\n"))


# --- template --------------------------------------------------------------------


def test_the_windows_template_is_the_default_one():
    assert template("win32") == DEFAULT_TEMPLATE
    assert template() == DEFAULT_TEMPLATE


def test_the_mac_template_speaks_mac():
    mac = template("darwin")
    hotkeys = mac.split("[hotkeys]\n")[1].split("\n[capture]")[0]
    assert "Option" in hotkeys and "Cmd" in hotkeys
    assert "F1–F20" in hotkeys
    assert "Win" not in mac
    assert "D:/" not in mac
    ui = mac.split("[ui]\n")[1].split("\n[debug]")[0]
    assert "跟随系统" in ui and "实底" in ui


def test_the_mac_template_uncommented_is_defaults_plus_examples(tmp_path):
    data = tomllib.loads(uncomment(template("darwin")))
    assert {name: set(table) for name, table in data.items()} == {name: set(keys) for name, keys in KNOWN_KEYS.items()}
    cfg, issues = build_config(data, source=tmp_path / "config.toml", platform="darwin")
    assert issues == []
    assert cfg == dataclasses.replace(
        AppConfig(),
        ocr=OcrEngineConfig(model_dir=cfg.ocr.model_dir),
        replacements=Replacements.from_mapping({"0CR": "OCR"}),
    )
    assert cfg.ocr.model_dir.is_absolute() and cfg.ocr.model_dir.parts[1] == "Users"


def test_the_mac_template_as_written_is_defaults(tmp_path):
    data = tomllib.loads(template("darwin"))
    assert data == {name: {} for name in KNOWN_KEYS}
    assert build_config(data, source=tmp_path / "c.toml", platform="darwin") == (AppConfig(), [])


def test_unknown_platform():
    with pytest.raises(ValueError, match="linux"):
        template("linux")


# --- reading -----------------------------------------------------------------------

MIXED = '[hotkeys]\ncapture = "Cmd+Shift+1"\nocr = "Win+2"\ntranslate = "Option+3"\n'


def test_a_mac_reads_cmd_and_rejects_win(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(MIXED, encoding="utf-8")
    result = load_config_file(path, platform="darwin")
    hk = result.config.hotkeys
    assert hk[Command.CAPTURE] == Hotkey(MOD_CMD | MOD_SHIFT, 0x31)
    assert hk[Command.OCR] == DEFAULT_HOTKEYS[Command.OCR]
    assert hk[Command.TRANSLATE] == Hotkey(MOD_ALT, 0x33)
    assert hk[Command.TRANSLATE_TEXT] == DEFAULT_HOTKEYS[Command.TRANSLATE_TEXT]
    assert [(i.key_path, "'Win'" in i.reason and "macOS" in i.reason) for i in result.issues] == [("hotkeys.ocr", True)]
    assert result.issues[0].reason.endswith("using Alt+2")


def test_windows_reads_win_and_rejects_cmd(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(MIXED, encoding="utf-8")
    result = load_config_file(path, platform="win32")
    hk = result.config.hotkeys
    assert hk[Command.CAPTURE] == DEFAULT_HOTKEYS[Command.CAPTURE]
    assert hk[Command.OCR] == Hotkey(MOD_CMD, 0x32)  # the Win bit
    assert hk[Command.TRANSLATE] == Hotkey(MOD_ALT, 0x33)
    assert [i.key_path for i in result.issues] == ["hotkeys.capture"]
    assert "'Cmd'" in result.issues[0].reason and "macOS" in result.issues[0].reason
    assert load_config_file(path).config == result.config  # win32 is the default


def test_duplicate_message_uses_the_platforms_names(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[hotkeys]\ncapture = "Cmd+1"\nocr = "Command+1"\n', encoding="utf-8")
    (issue,) = load_config_file(path, platform="darwin").issues
    assert issue.key_path == "hotkeys.ocr"
    assert issue.reason.startswith("Cmd+1 is already used by hotkeys.capture")


def test_a_new_file_gets_the_platforms_template(tmp_path):
    path = tmp_path / "config.toml"
    assert load_config_file(path, platform="darwin").created
    assert path.read_text(encoding="utf-8") == template("darwin")


# --- writing back --------------------------------------------------------------------


def test_cmd_is_written_on_a_mac_and_option_as_alt(tmp_path):
    old = settings_of(AppConfig())
    hotkeys = dict(old.hotkeys) | {Command.CAPTURE: Hotkey(MOD_CMD | MOD_SHIFT, 0x31),
                                   Command.OCR: Hotkey(MOD_ALT | MOD_SHIFT, 0x32)}
    new = dataclasses.replace(old, hotkeys=hotkeys)
    delta = changes(old, new, platform="darwin")
    assert delta == {"hotkeys.capture": "Shift+Cmd+1", "hotkeys.ocr": "Alt+Shift+2"}
    assert changes(old, new)["hotkeys.capture"] == "Shift+Win+1"
    path = tmp_path / "config.toml"
    write_changes(path, delta, platform="darwin")  # missing file: starts from the Mac template
    text = path.read_text(encoding="utf-8")
    assert 'capture = "Shift+Cmd+1"' in text and "Win" not in text
    assert load_config_file(path, platform="darwin").config.hotkeys[Command.CAPTURE] == hotkeys[Command.CAPTURE]
