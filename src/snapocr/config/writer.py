"""Writing settings-window changes back into the config file (PRD F11-4, M3 plan D7).

Only the changed keys are touched. A key already set is changed in place by
``tomlkit``, keeping its position and any inline comment. A missing key goes
where the template expects it: its commented-out ``# key = ...`` line in the
section is replaced, otherwise it goes on the line after the section header;
a section without a plain header is left to ``tomlkit``; a missing section is
appended. ``tomlkit`` alone would append the key at the end of the table, after
a commented-out ``# [postprocess.replacements]`` header, where it would become
a replacement entry once that header is uncommented.

The new text must read back (``tomllib``) as the old data plus the changes;
otherwise nothing is written. Writing goes through a temporary file in the
same directory and ``os.replace``, so a failure leaves the old file as it was.
"""

from __future__ import annotations

import copy
import os
import re
import tempfile
import tomllib
from collections.abc import Mapping
from pathlib import Path

import tomlkit

from snapocr.config.template import template

_HEADER = r"\s*\[\s*{name}\s*\]\s*(#.*)?"
_ANY_HEADER = re.compile(r"\s*#?\s*\[")  # a table header, real or commented out
_COMMENTED = r"#\s*{key}\s*="


class ConfigWriteError(Exception):
    """The file was left unchanged; the message is shown in the settings window."""


def _read(path: Path, platform: str) -> str:
    if not path.exists():
        return template(platform)
    try:
        raw = path.read_bytes()
    except OSError as e:
        raise ConfigWriteError(f"无法读取配置文件：{e.strerror or e}") from None
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ConfigWriteError("配置文件不是 UTF-8 编码，请先用“高级设置”打开配置文件修好。") from None


def _parse(text: str) -> dict:
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise ConfigWriteError(f"配置文件有语法错误（{e}），请先用“高级设置”打开配置文件修好。") from None


def _split(dotted: str) -> tuple[str, str]:
    section, key = dotted.split(".")
    return section, key


def _set_active(text: str, changes: Mapping[str, bool | str]) -> tuple[str, dict[str, bool | str]]:
    """Change the keys that are already set; returns the new text and the keys still missing."""
    doc = tomlkit.parse(text)
    missing: dict[str, bool | str] = {}
    for dotted, value in changes.items():
        section, key = _split(dotted)
        table = doc.get(section)
        if section in doc and not isinstance(table, Mapping):
            raise ConfigWriteError(f"配置文件里的 [{section}] 不是表，请在配置文件里手动修改。")
        if table is not None and key in table:
            table[key] = value
        else:
            missing[dotted] = value
    return doc.as_string(), missing


def _insert(text: str, section: str, key: str, value: bool | str) -> str:
    nl = "\r\n" if "\r\n" in text else "\n"
    entry = f"{key} = {tomlkit.item(value).as_string()}"
    lines = text.splitlines(keepends=True)
    header = re.compile(_HEADER.format(name=re.escape(section)))
    start = next((i for i, ln in enumerate(lines) if header.fullmatch(ln.rstrip("\r\n"))), None)
    if start is None:
        if section in tomlkit.parse(text):  # dotted keys, an inline table or only sub-tables
            doc = tomlkit.parse(text)
            doc[section][key] = value
            return doc.as_string()
        if text and not text.endswith("\n"):
            text += nl
        return f"{text}[{section}]{nl}{entry}{nl}"
    if not lines[start].endswith("\n"):
        lines[start] += nl
    commented = re.compile(_COMMENTED.format(key=re.escape(key)))
    for i in range(start + 1, len(lines)):
        if _ANY_HEADER.match(lines[i]):
            break
        if commented.match(lines[i]):
            ending = lines[i][len(lines[i].rstrip("\r\n")):]
            lines[i] = entry + ending
            return "".join(lines)
    lines.insert(start + 1, entry + nl)
    return "".join(lines)


def _replace_file(path: Path, text: str) -> None:
    try:
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    except OSError as e:
        raise ConfigWriteError(f"无法写入配置文件：{e.strerror or e}") from None
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(text.encode("utf-8"))
        os.replace(tmp, path)
    except OSError as e:
        os.unlink(tmp)
        raise ConfigWriteError(f"无法写入配置文件：{e.strerror or e}") from None


def write_changes(path: Path, changes: Mapping[str, bool | str], *, platform: str = "win32") -> None:
    """Write "section.key" -> value into ``path``; ``ConfigWriteError`` leaves the file unchanged.

    A missing file starts from ``platform``'s template (M9 WI-5)."""
    text = _read(path, platform)
    expected = copy.deepcopy(_parse(text))
    text, missing = _set_active(text, changes)
    for dotted, value in missing.items():
        text = _insert(text, *_split(dotted), value)
    for dotted, value in changes.items():
        section, key = _split(dotted)
        expected.setdefault(section, {})[key] = value
    try:
        written = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        written = None
    if written != expected:
        raise ConfigWriteError("无法安全地改写配置文件，请用“高级设置”打开配置文件手动修改。")
    _replace_file(path, text)
