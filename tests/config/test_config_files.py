"""M2 WI-7: default template and config file I/O (PRD F9-1, F9-2, F9-3; M2 plan D9).

Template convention: lines starting with "## " are explanations; lines starting
with "# " are settings commented out, so removing the leading "# " enables them.
Removing it from every such line gives the defaults, plus the two examples for
settings whose default is "not set": ``ocr.model_dir`` and one replacement.
"""

import dataclasses
import os
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


@pytest.mark.windows
def test_template_uncommented_is_defaults_plus_examples():
    data = tomllib.loads(uncomment(DEFAULT_TEMPLATE))
    cfg, issues = build_config(data, source=REPO / "config.local.toml")
    assert issues == []
    assert cfg == dataclasses.replace(
        AppConfig(),
        ocr=OcrEngineConfig(model_dir=EXAMPLE_MODEL_DIR),
        replacements=Replacements.from_mapping({"0CR": "OCR"}),
    )


@pytest.mark.macos
def test_template_uncommented_is_defaults_plus_examples_mac():
    """M9 WI-1 (plan D8): the example folder is a Windows spelling, so on a Mac it is
    relative and, like any relative ``model_dir``, read next to the config file."""
    data = tomllib.loads(uncomment(DEFAULT_TEMPLATE))
    cfg, issues = build_config(data, source=REPO / "config.local.toml")
    assert issues == []
    assert cfg == dataclasses.replace(
        AppConfig(),
        ocr=OcrEngineConfig(model_dir=REPO / EXAMPLE_MODEL_DIR),
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


def test_default_config_path_follows_snapocr_config(monkeypatch, tmp_path):
    monkeypatch.setenv("SNAPOCR_CONFIG", str(tmp_path / "env.toml"))
    assert default_config_path() == tmp_path / "env.toml"


def test_default_config_path_without_the_variable(monkeypatch, tmp_path):
    """F21-1: this checkout is a source root, so its config.local.toml is used only when present."""
    monkeypatch.delenv("SNAPOCR_CONFIG", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    source_file = REPO / "config.local.toml"
    expected = source_file if source_file.exists() else tmp_path / "snapocr" / "config.toml"
    assert default_config_path() == expected


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


def test_missing_directories_are_created_first(tmp_path):
    """F21-3 (v1.8): first run with %APPDATA%/snapocr not there yet."""
    path = tmp_path / "AppData" / "Roaming" / "snapocr" / "config.toml"
    assert load_config_file(path) == LoadResult(AppConfig(), [], created=True)
    assert path.read_bytes() == DEFAULT_TEMPLATE.encode("utf-8")


def test_cannot_create_reports_and_uses_defaults(tmp_path):
    """A file where a directory should be: the directory cannot be made (F21-3, F9-2)."""
    (tmp_path / "blocker").write_text("x", encoding="utf-8")
    path = tmp_path / "blocker" / "snapocr" / "config.toml"
    result = load_config_file(path)
    assert result.config == AppConfig()
    assert result.created is False
    (issue,) = result.issues
    assert issue.file == path and issue.reason
    assert (tmp_path / "blocker").read_text(encoding="utf-8") == "x"


@pytest.mark.parametrize("content", [b"", b"\xef\xbb\xbf", b"# only a comment\n"])
def test_empty_file_is_defaults(tmp_path, content):
    path = tmp_path / "config.local.toml"
    path.write_bytes(content)
    assert load_config_file(path) == LoadResult(AppConfig(), [], created=False)


# --- WI-19: single-instance name per config file (plan D5) --------------------------

import re  # noqa: E402

from snapocr.config.files import instance_name  # noqa: E402


def test_instance_name_format(tmp_path):
    name = instance_name(tmp_path / "config.local.toml")
    assert re.fullmatch(r"Local\\snapocr-[0-9a-f]{12}", name)


@pytest.mark.windows
def test_instance_name_ignores_case_and_relative_spelling(tmp_path, monkeypatch):
    path = tmp_path / "Config.Local.TOML"
    monkeypatch.chdir(tmp_path)
    assert instance_name(path) == instance_name(Path(str(path).upper())) == instance_name(Path("Config.Local.TOML"))


def test_instance_name_ignores_relative_spelling(tmp_path, monkeypatch):
    """M9 WI-1: the half of the rule above that holds on every system."""
    path = tmp_path / "config.local.toml"
    monkeypatch.chdir(tmp_path)
    assert instance_name(path) == instance_name(Path("config.local.toml")) == instance_name(Path("./x/../config.local.toml"))


def test_instance_name_differs_per_file(tmp_path):
    assert instance_name(tmp_path / "a.toml") != instance_name(tmp_path / "b.toml")


def test_default_config_gets_a_stable_name():
    assert instance_name(default_config_path()) == instance_name(default_config_path())


# --- M9 WI-11: the Mac lock file uses the same key (F23-8, plan D18) ---------------------

from hypothesis import given  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

from snapocr.config.files import instance_key, lock_path  # noqa: E402


def test_instance_name_is_unchanged_by_the_key_refactor(tmp_path):
    """The Windows mutex name stays exactly what M2 produced (hash of the case-folded resolved path)."""
    import hashlib

    path = tmp_path / "config.local.toml"
    key = os.path.normcase(str(path.resolve()))
    assert instance_name(path) == "Local\\snapocr-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def test_lock_path_is_in_the_given_dir(tmp_path):
    path = tmp_path / "config.local.toml"
    lock = lock_path(path, tmp_path / "locks")
    assert lock == tmp_path / "locks" / f"snapocr-{instance_key(path)}.lock"
    assert re.fullmatch(r"snapocr-[0-9a-f]{12}\.lock", lock.name)


def test_lock_path_differs_per_file(tmp_path):
    assert lock_path(tmp_path / "a.toml", tmp_path) != lock_path(tmp_path / "b.toml", tmp_path)


def test_lock_path_ignores_relative_spelling(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert lock_path(tmp_path / "c.toml", tmp_path) == lock_path(Path("./x/../c.toml"), tmp_path)


@given(st.text(alphabet=st.characters(categories=["L", "N"]), min_size=1, max_size=20))
def test_mutex_name_and_lock_file_share_one_key(name):
    path = Path("/cfg") / f"{name}.toml"
    key = instance_key(path)
    assert re.fullmatch(r"[0-9a-f]{12}", key)
    assert instance_name(path) == f"Local\\snapocr-{key}"
    assert lock_path(path, Path("/locks")).name == f"snapocr-{key}.lock"


# --- M4 WI-22: [capture] save_dir (F17-2) ------------------------------------------------


def test_template_capture_section_after_hotkeys_with_its_help():
    headers = [line for line in DEFAULT_TEMPLATE.split("\n") if line.startswith("[")]
    assert headers[:3] == ["[hotkeys]", "[capture]", "[ocr]"]
    section = DEFAULT_TEMPLATE.split("[capture]\n")[1].split("\n[ocr]")[0]
    assert "绝对路径" in section and "/" in section
    assert tomllib.loads(uncomment(section)) == {"save_dir": str(AppConfig().save_dir)}


@pytest.mark.windows
def test_cannot_create_the_file_in_an_existing_directory(tmp_path):
    """The directory is fine but the file cannot be made ("?" is not allowed in Windows names)."""
    path = tmp_path / "bad?name.toml"
    result = load_config_file(path)
    assert result.config == AppConfig() and result.created is False
    (issue,) = result.issues
    assert issue.file == path and issue.reason.startswith("could not create the default config file")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.macos
def test_cannot_create_the_file_in_an_existing_directory_mac(tmp_path):
    """M9 WI-1: "?" is a fine Mac file name, so here the folder itself refuses new files."""
    folder = tmp_path / "read-only"
    folder.mkdir()
    folder.chmod(0o555)
    try:
        path = folder / "config.local.toml"
        result = load_config_file(path)
        listing = list(folder.iterdir())
    finally:
        folder.chmod(0o755)
    assert result.config == AppConfig() and result.created is False
    (issue,) = result.issues
    assert issue.file == path and issue.reason.startswith("could not create the default config file")
    assert listing == []
