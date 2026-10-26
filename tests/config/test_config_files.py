"""M2 WI-7: default template and config file I/O (PRD F9-1, F9-2, F9-3; M2 plan D9).

Template convention: lines starting with "## " are explanations; lines starting
with "# " are settings commented out, so removing the leading "# " enables them.
Removing it from every such line gives the defaults, plus the two examples for
settings whose default is "not set": ``ocr.model_dir`` and one replacement.
"""

import dataclasses
import tomllib
from pathlib import Path

import pytest

from snapocr.config.files import LoadResult, default_config_path, load_config_file
from snapocr.config.load import build_config
from snapocr.config.schema import KNOWN_KEYS, AppConfig
from snapocr.config.template import DEFAULT_TEMPLATE
from snapocr.engines.config import OcrEngineConfig
from snapocr.postprocess import Replacements

REPO = Path(__file__).resolve().parents[2]
EXAMPLE_MODEL_DIR = Path("D:/LLM/models/rapidocr")


def uncomment(template: str) -> str:
    return "\n".join(line[2:] if line.startswith("# ") else line for line in template.split("\n"))


# --- template --------------------------------------------------------------------


def test_template_lines_follow_convention():
    for line in DEFAULT_TEMPLATE.split("\n"):
        assert (
            line == ""
            or line.startswith("## ")
            or line.startswith("# ")
            or (line.startswith("[") and line.endswith("]"))
        ), line


def test_template_has_chinese_explanations():
    explanations = [line for line in DEFAULT_TEMPLATE.split("\n") if line.startswith("## ")]
    assert len(explanations) >= len(KNOWN_KEYS)
    assert all(any("\u4e00" <= ch <= "\u9fff" for ch in line) for line in explanations[:3])


def test_template_as_written_is_defaults():
    data = tomllib.loads(DEFAULT_TEMPLATE)
    assert data == {name: {} for name in KNOWN_KEYS}
    cfg, issues = build_config(data, source=REPO / "config.local.toml")
    assert issues == []
    assert cfg == AppConfig()


def test_template_uncommented_is_defaults_plus_examples():
    data = tomllib.loads(uncomment(DEFAULT_TEMPLATE))
    cfg, issues = build_config(data, source=REPO / "config.local.toml")
    assert issues == []
    assert cfg == dataclasses.replace(
        AppConfig(),
        ocr=OcrEngineConfig(model_dir=EXAMPLE_MODEL_DIR),
        replacements=Replacements.from_mapping({"0CR": "OCR"}),
    )


def test_template_keys_equal_schema_keys():
    data = tomllib.loads(uncomment(DEFAULT_TEMPLATE))
    assert {name: set(table) for name, table in data.items()} == {
        name: set(keys) for name, keys in KNOWN_KEYS.items()
    }


def test_template_ends_with_newline_and_no_crlf():
    assert DEFAULT_TEMPLATE.endswith("\n")
    assert "\r" not in DEFAULT_TEMPLATE


# --- files -----------------------------------------------------------------------


def test_default_config_path():
    assert default_config_path() == REPO / "config.local.toml"


def test_missing_file_is_created_and_never_overwritten(tmp_path):
    path = tmp_path / "config.local.toml"
    first = load_config_file(path)
    assert first == LoadResult(AppConfig(), [], created=True)
    assert path.read_bytes() == DEFAULT_TEMPLATE.encode("utf-8")
    stamp = path.stat().st_mtime_ns

    second = load_config_file(path)
    assert second == LoadResult(AppConfig(), [], created=False)
    assert path.read_bytes() == DEFAULT_TEMPLATE.encode("utf-8")
    assert path.stat().st_mtime_ns == stamp


def test_existing_file_is_loaded_not_touched(tmp_path):
    path = tmp_path / "config.local.toml"
    content = '[ocr]\nmin_score = 0.7\n\n[hotkeys]\nocr = "Alt+Foo"\n'.encode("utf-8")
    path.write_bytes(content)
    result = load_config_file(path)
    assert result.created is False
    assert result.config.ocr.min_score == 0.7
    assert [i.key_path for i in result.issues] == ["hotkeys.ocr"]
    assert result.issues[0].file == path
    assert path.read_bytes() == content


def test_bom_file_loads(tmp_path):
    path = tmp_path / "config.local.toml"
    path.write_bytes(b"\xef\xbb\xbf[ocr]\r\nmin_score = 0.25\r\n")
    result = load_config_file(path)
    assert result.issues == []
    assert result.config.ocr.min_score == 0.25


def test_syntax_error_uses_defaults_and_keeps_file(tmp_path):
    path = tmp_path / "config.local.toml"
    content = '[ocr]\nmin_score = 0.7\nmodel_dir = "unterminated\n'.encode("utf-8")
    path.write_bytes(content)
    result = load_config_file(path)
    assert result.config == AppConfig()
    assert result.created is False
    (issue,) = result.issues
    assert issue.file == path
    assert issue.key_path == ""
    assert "line 3" in issue.reason
    assert "column" in issue.reason
    assert path.read_bytes() == content


def test_not_utf8_reported(tmp_path):
    path = tmp_path / "config.local.toml"
    path.write_bytes(b"[ocr]\nmodel_dir = '\xff\xfe'\n")
    result = load_config_file(path)
    assert result.config == AppConfig()
    (issue,) = result.issues
    assert issue.file == path and "UTF-8" in issue.reason
    assert path.read_bytes() == b"[ocr]\nmodel_dir = '\xff\xfe'\n"


def test_directory_in_place_of_file(tmp_path):
    path = tmp_path / "config.local.toml"
    path.mkdir()
    result = load_config_file(path)
    assert result.config == AppConfig()
    assert result.created is False
    (issue,) = result.issues
    assert issue.file == path and issue.reason
    assert path.is_dir()


def test_cannot_create_reports_and_uses_defaults(tmp_path):
    path = tmp_path / "no-such-dir" / "config.local.toml"
    result = load_config_file(path)
    assert result.config == AppConfig()
    assert result.created is False
    (issue,) = result.issues
    assert issue.file == path and issue.reason
    assert not path.parent.exists()


@pytest.mark.parametrize("content", [b"", b"\xef\xbb\xbf", b"# only a comment\n"])
def test_empty_file_is_defaults(tmp_path, content):
    path = tmp_path / "config.local.toml"
    path.write_bytes(content)
    assert load_config_file(path) == LoadResult(AppConfig(), [], created=False)
