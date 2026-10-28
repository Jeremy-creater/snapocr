"""M3 WI-2: writing settings back into config.local.toml (PRD F11-4; M3 plan D7).

Pinned here (beyond the plan text):
- A commented ``# key = ...`` line counts only inside its section, before the
  next table header (real or commented out); one after ``# [postprocess.replacements]``
  belongs to that table and is left alone.
- Errors are ``ConfigWriteError`` with a Chinese message for the settings
  window; the file's bytes are unchanged and no temporary file is left.
- When the written text would not read back as "old data + changes" (for
  example a header-like line inside a multi-line string), nothing is written.
"""

import os
import tomllib
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from snapocr.commands import Command
from snapocr.config.files import load_config_file
from snapocr.config.settings import changes, settings_of
from snapocr.config.template import DEFAULT_TEMPLATE
from snapocr.config.writer import ConfigWriteError, write_changes
from snapocr.hotkeys import parse_hotkey
from support.settings_strategies import window_settings

CHANGES = {"hotkeys.capture": "Ctrl+Q", "postprocess.spacing": False, "translator.target_lang": "en"}


def write(path: Path, text: str) -> Path:
    path.write_bytes(text.encode("utf-8"))
    return path


def read(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def data(path: Path) -> dict:
    return tomllib.loads(path.read_bytes().decode("utf-8-sig"))


def test_missing_file_starts_from_template(tmp_path):
    path = tmp_path / "config.local.toml"
    write_changes(path, CHANGES)
    lines, template = read(path).split("\n"), DEFAULT_TEMPLATE.split("\n")
    assert len(lines) == len(template)
    diff = {i: (template[i], lines[i]) for i in range(len(lines)) if lines[i] != template[i]}
    assert sorted(new for _, new in diff.values()) == [
        'capture = "Ctrl+Q"',
        "spacing = false",
        'target_lang = "en"',
    ]
    assert {old for old, _ in diff.values()} == {'# capture = "Alt+1"', "# spacing = true", '# target_lang = "auto"'}
    loaded = load_config_file(path)
    assert loaded.issues == []
    got = settings_of(loaded.config)
    assert got.hotkeys[Command.CAPTURE] == parse_hotkey("Ctrl+Q")
    assert (got.spacing, got.target_lang) == (False, "en")
    assert data(path) == {
        "hotkeys": {"capture": "Ctrl+Q"},
        "capture": {},  # M4 WI-22: and a [capture] section
        "ocr": {},
        "postprocess": {"spacing": False},
        "notify": {},  # M3 WI-11: the template has a [notify] section
        "ui": {},  # M7 WI-1: and a [ui] section
        "debug": {},  # M3 WI-12: and a [debug] section
        "translator": {"target_lang": "en"},
    }


def test_active_key_keeps_position_and_inline_comment(tmp_path):
    path = write(tmp_path / "c.toml", '# top\n[postprocess]\nparagraphs = false\nspacing = true  # mine\nx = 1\n')
    write_changes(path, {"postprocess.spacing": False})
    assert read(path) == '# top\n[postprocess]\nparagraphs = false\nspacing = false  # mine\nx = 1\n'


def test_key_absent_inserted_under_header(tmp_path):
    path = write(tmp_path / "c.toml", '[translator]\n## help\nmodel = "x"\n# [translator.sampling]\n')
    write_changes(path, {"translator.target_lang": "zh"})
    assert read(path) == '[translator]\ntarget_lang = "zh"\n## help\nmodel = "x"\n# [translator.sampling]\n'


def test_commented_key_after_commented_subtable_is_not_used(tmp_path):
    text = "[postprocess]\n# [postprocess.replacements]\n# spacing = true\n"
    path = write(tmp_path / "c.toml", text)
    write_changes(path, {"postprocess.spacing": False})
    assert read(path) == "[postprocess]\nspacing = false\n# [postprocess.replacements]\n# spacing = true\n"


def test_commented_key_in_next_section_is_not_used(tmp_path):
    path = write(tmp_path / "c.toml", '[hotkeys]\n[translator]\n# capture = "Alt+1"\n')
    write_changes(path, {"hotkeys.capture": "Ctrl+Q"})
    assert read(path) == '[hotkeys]\ncapture = "Ctrl+Q"\n[translator]\n# capture = "Alt+1"\n'


def test_header_with_spaces_and_comment(tmp_path):
    path = write(tmp_path / "c.toml", "  [ postprocess ]  # pp\n# spacing = true\n")
    write_changes(path, {"postprocess.spacing": False})
    assert read(path) == "  [ postprocess ]  # pp\nspacing = false\n"


def test_section_absent_appended(tmp_path):
    path = write(tmp_path / "c.toml", '[hotkeys]\nocr = "Alt+2"')  # no final newline
    write_changes(path, {"postprocess.spacing": False, "postprocess.punctuation": False})
    assert read(path) == '[hotkeys]\nocr = "Alt+2"\n[postprocess]\npunctuation = false\nspacing = false\n'
    assert data(path)["postprocess"] == {"spacing": False, "punctuation": False}


def test_header_last_line_without_newline(tmp_path):
    path = write(tmp_path / "c.toml", "[postprocess]")
    write_changes(path, {"postprocess.spacing": False})
    assert read(path) == "[postprocess]\nspacing = false\n"


def test_empty_file(tmp_path):
    path = write(tmp_path / "c.toml", "")
    write_changes(path, {"translator.model": "qwen3:8b"})
    assert data(path) == {"translator": {"model": "qwen3:8b"}}


@pytest.mark.parametrize(
    "text",
    [
        "[translator.sampling]\ntemperature = 0.5\n",
        'translator = { timeout_s = 30 }\n',
        "translator.timeout_s = 30\n",
    ],
)
def test_section_without_plain_header(tmp_path, text):
    path = write(tmp_path / "c.toml", text)
    before = data(path)
    write_changes(path, {"translator.model": "qwen3:8b"})
    after = data(path)
    assert after["translator"].pop("model") == "qwen3:8b"
    assert after == before


def test_section_not_a_table(tmp_path):
    path = write(tmp_path / "c.toml", "postprocess = 5\n")
    with pytest.raises(ConfigWriteError):
        write_changes(path, {"postprocess.spacing": False})
    assert read(path) == "postprocess = 5\n"


def test_strings_are_escaped(tmp_path):
    path = write(tmp_path / "c.toml", "")
    model = 'my"model\\x:7b'
    write_changes(path, {"translator.model": model})
    assert data(path)["translator"]["model"] == model


def test_crlf_kept(tmp_path):
    path = write(tmp_path / "c.toml", DEFAULT_TEMPLATE.replace("\n", "\r\n"))
    write_changes(path, CHANGES)
    raw = read(path)
    assert raw.count("\n") == raw.count("\r\n") == DEFAULT_TEMPLATE.count("\n")
    assert data(path)["hotkeys"] == {"capture": "Ctrl+Q"}


def test_bom_file(tmp_path):
    path = tmp_path / "c.toml"
    path.write_bytes(b"\xef\xbb\xbf[postprocess]\n# spacing = true\n")
    write_changes(path, {"postprocess.spacing": False})
    loaded = load_config_file(path)
    assert loaded.issues == []
    assert loaded.config.postprocess.spacing is False


def test_unicode_kept(tmp_path):
    path = write(tmp_path / "c.toml", "## 中文说明\n[postprocess]\n")
    write_changes(path, {"postprocess.spacing": False})
    assert read(path) == "## 中文说明\n[postprocess]\nspacing = false\n"


def _unchanged_on_error(path: Path, before: bytes):
    assert path.read_bytes() == before
    assert sorted(p.name for p in path.parent.iterdir()) == [path.name]


def test_syntax_error_refused(tmp_path):
    path = write(tmp_path / "c.toml", "[postprocess\nspacing = true\n")
    before = path.read_bytes()
    with pytest.raises(ConfigWriteError, match="语法错误"):
        write_changes(path, {"postprocess.spacing": False})
    _unchanged_on_error(path, before)


def test_not_utf8_refused(tmp_path):
    path = tmp_path / "c.toml"
    path.write_bytes(b"## \xff\n")
    with pytest.raises(ConfigWriteError, match="UTF-8"):
        write_changes(path, {"postprocess.spacing": False})
    _unchanged_on_error(path, b"## \xff\n")


def test_unreadable_refused(tmp_path):
    path = tmp_path / "c.toml"
    path.mkdir()
    with pytest.raises(ConfigWriteError, match="读取"):
        write_changes(path, {"postprocess.spacing": False})
    assert path.is_dir()


def test_header_inside_multiline_string_is_refused(tmp_path):
    text = '[translator]\nprompt_template = """\n[postprocess]\n{source_text}"""\n'
    path = write(tmp_path / "c.toml", text)
    before = path.read_bytes()
    with pytest.raises(ConfigWriteError, match="手动"):
        write_changes(path, {"postprocess.spacing": False})
    _unchanged_on_error(path, before)


def test_replace_failure_leaves_file_and_no_temp(tmp_path, monkeypatch):
    path = write(tmp_path / "c.toml", "[postprocess]\n")
    before = path.read_bytes()

    def fail(src, dst):
        raise PermissionError(13, "Access is denied")

    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(ConfigWriteError, match="Access is denied"):
        write_changes(path, {"postprocess.spacing": False})
    _unchanged_on_error(path, before)


def test_temp_write_failure(tmp_path):
    path = tmp_path / "missing-dir" / "c.toml"
    with pytest.raises(ConfigWriteError, match="写入"):
        write_changes(path, {"postprocess.spacing": False})
    assert not path.parent.exists()


def test_no_changes_still_valid(tmp_path):
    path = write(tmp_path / "c.toml", "[postprocess]\nspacing = true\n")
    write_changes(path, {})
    assert read(path) == "[postprocess]\nspacing = true\n"


# --- property: template with random active keys, random settings ----------------------

_WINDOW_KEYS = {"capture", "ocr", "translate", "translate_text", "code_ocr", "table_ocr", "paragraphs", "spacing", "punctuation",
                "model", "target_lang"}


def _setting_lines() -> list[str]:
    """The template's commented-out lines of the settings-window keys."""
    return [ln for ln in DEFAULT_TEMPLATE.split("\n") if ln.startswith("# ") and ln[2:].split(" = ")[0] in _WINDOW_KEYS]


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(st.sets(st.sampled_from(_setting_lines())), window_settings())
def test_template_roundtrip(tmp_path, active, new):
    assert len(_setting_lines()) == 11  # M3 WI-14 added code_ocr, M4 WI-15 table_ocr
    text = "\n".join(line[2:] if line in active else line for line in DEFAULT_TEMPLATE.split("\n"))
    path = write(tmp_path / "config.local.toml", text)
    old_config = load_config_file(path).config
    delta = changes(settings_of(old_config), new)
    write_changes(path, delta)
    loaded = load_config_file(path)
    assert loaded.issues == []
    assert settings_of(loaded.config) == new
    assert loaded.config.ocr == old_config.ocr
    assert loaded.config.translator.prompt_template == old_config.translator.prompt_template
    out = read(path).split("\n")
    assert [ln for ln in out if ln.startswith("##")] == [ln for ln in text.split("\n") if ln.startswith("##")]
    touched = {d.split(".")[1] for d in delta}
    kept = [ln for ln in text.split("\n") if ln.lstrip("# ").split(" = ")[0] not in touched]
    assert [ln for ln in out if ln.lstrip("# ").split(" = ")[0] not in touched] == kept


def test_commented_line_inside_multiline_string_is_refused(tmp_path):
    """Replacing that line drops the closing quotes; the result does not parse."""
    text = '[translator]\nprompt_template = """{source_text}\n[postprocess]\n# spacing = true"""\n'
    path = write(tmp_path / "c.toml", text)
    before = path.read_bytes()
    with pytest.raises(ConfigWriteError, match="手动"):
        write_changes(path, {"postprocess.spacing": False})
    _unchanged_on_error(path, before)
