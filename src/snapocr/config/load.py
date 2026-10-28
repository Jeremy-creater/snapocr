"""Build an ``AppConfig`` from parsed TOML data (PRD F9-3, M2 plan D9). Never raises.

Fallback rules: an unknown key or section is reported (with a close-match
suggestion) and ignored; a bad value is reported and only that key uses its
default. A section that is not a table uses its defaults. A hotkey that is
invalid or duplicates an earlier one (in ``Command`` order) falls back to its
default; if that default is taken too, the hotkey is disabled.
"""

from __future__ import annotations

import difflib
import numbers
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

from snapocr.commands import Command
from snapocr.config.schema import (
    DEFAULT_HOTKEY_TEXT,
    DEFAULT_HOTKEYS,
    HOTKEY_COMMANDS,
    KNOWN_KEYS,
    RENAMED_KEYS,
    AppConfig,
    ConfigIssue,
    default_save_dir,
)
from snapocr.engines.config import OcrEngineConfig
from snapocr.hotkeys import Hotkey, HotkeyError, format_hotkey, parse_hotkey
from snapocr.postprocess import PostprocessOptions, ReplacementError, Replacements
from snapocr.translators.config import TranslatorConfig
from snapocr.translators.errors import TranslatorConfigError


class _Issues:
    def __init__(self, source: Path) -> None:
        self.source = source
        self.items: list[ConfigIssue] = []

    def add(self, key_path: str, reason: str) -> None:
        self.items.append(ConfigIssue(self.source, key_path, reason))


def _unknown(issues: _Issues, key_path: str, name: object, known: tuple[str, ...], what: str) -> None:
    reason = f"unknown {what}, ignored"
    close = difflib.get_close_matches(str(name), known, n=1)
    if close:
        reason += f"; did you mean {close[0]!r}?"
    issues.add(key_path, reason)


def _section(data: Mapping, name: str, issues: _Issues) -> Mapping:
    """The section's table with unknown keys reported; {} when absent or not a table."""
    if name not in data:
        return {}
    table = data[name]
    if not isinstance(table, Mapping):
        issues.add(name, f"must be a table, got {type(table).__name__}; using defaults")
        return {}
    known = KNOWN_KEYS[name]
    for key in table:
        if (name, key) in RENAMED_KEYS:
            issues.add(f"{name}.{key}", f"renamed to {RENAMED_KEYS[name, key]!r}, ignored")
        elif key not in known:
            _unknown(issues, f"{name}.{key}", key, known, "key")
    return {k: table[k] for k in known if k in table}


def _hotkeys(table: Mapping, issues: _Issues) -> Mapping[Command, Hotkey]:
    chosen: dict[Command, Hotkey] = {}
    owner: dict[Hotkey, Command] = {}
    for command in HOTKEY_COMMANDS:
        path = f"hotkeys.{command.value}"
        default = DEFAULT_HOTKEYS[command]
        hotkey = default
        if command.value in table:
            text = table[command.value]
            if not isinstance(text, str):
                issues.add(path, f"must be a string like {DEFAULT_HOTKEY_TEXT[command]!r}, "
                                 f"got {type(text).__name__}; using {DEFAULT_HOTKEY_TEXT[command]}")
            else:
                try:
                    hotkey = parse_hotkey(text)
                except HotkeyError as e:
                    issues.add(path, f"{e}; using {DEFAULT_HOTKEY_TEXT[command]}")
                else:
                    if hotkey in owner:
                        issues.add(path, f"{format_hotkey(hotkey)} is already used by "
                                         f"hotkeys.{owner[hotkey].value}; using {DEFAULT_HOTKEY_TEXT[command]}")
                        hotkey = default
        if hotkey in owner:
            issues.add(path, f"default {format_hotkey(hotkey)} is used by hotkeys.{owner[hotkey].value}; "
                             "this hotkey is disabled")
            continue
        chosen[command] = hotkey
        owner[hotkey] = command
    return MappingProxyType(chosen)


def _is_real(value: object) -> bool:
    return isinstance(value, numbers.Real) and not isinstance(value, bool)


def _save_dir(table: Mapping, issues: _Issues) -> Path:
    """F17-2: an absolute folder; unlike ocr.model_dir, a relative one is an error."""
    default = default_save_dir()
    if "save_dir" not in table:
        return default
    v = table["save_dir"]
    if isinstance(v, str) and Path(v).is_absolute():
        return Path(v)
    issues.add("capture.save_dir", f"must be an absolute folder path, got {v!r}; using {default}")
    return default


def _ocr(table: Mapping, issues: _Issues, source: Path) -> OcrEngineConfig:
    defaults = OcrEngineConfig()
    min_score = defaults.min_score
    model_dir = defaults.model_dir
    if "min_score" in table:
        v = table["min_score"]
        # Range check by comparison: nan fails it and huge ints do not overflow.
        if _is_real(v) and 0 <= v <= 1:
            min_score = float(v)
        else:
            issues.add("ocr.min_score", f"must be a number in [0, 1], got {v!r}; using {defaults.min_score}")
    if "model_dir" in table:
        v = table["model_dir"]
        if isinstance(v, str) and v.strip():
            model_dir = source.parent / v
        else:
            issues.add("ocr.model_dir", f"must be a non-empty path string, got {v!r}; using the bundled models")
    return OcrEngineConfig(min_score=min_score, model_dir=model_dir)


def _postprocess(table: Mapping, issues: _Issues) -> tuple[PostprocessOptions, Replacements]:
    defaults = PostprocessOptions()
    switches = {}
    for name in ("paragraphs", "spacing", "punctuation"):
        if name in table:
            v = table[name]
            if type(v) is bool:
                switches[name] = v
            else:
                issues.add(f"postprocess.{name}", f"must be true or false, got {v!r}; "
                                                  f"using {str(getattr(defaults, name)).lower()}")
    replacements = Replacements.EMPTY
    if "replacements" in table:
        v = table["replacements"]
        if not isinstance(v, Mapping):
            issues.add("postprocess.replacements", f"must be a table, got {type(v).__name__}; no replacements")
        else:
            try:
                replacements = Replacements.from_mapping(v)
            except ReplacementError as e:
                issues.add("postprocess.replacements", f"{e}; the whole table is ignored")
    return PostprocessOptions(**switches), replacements


def _bool(table: Mapping, section: str, key: str, default: bool, issues: _Issues) -> bool:
    if key not in table:
        return default
    v = table[key]
    if type(v) is bool:
        return v
    issues.add(f"{section}.{key}", f"must be true or false, got {v!r}; using {str(default).lower()}")
    return default


def _translator(table: Mapping, issues: _Issues) -> TranslatorConfig:
    """Drop each field TranslatorConfig rejects and retry; the defaults are valid, so this ends."""
    kwargs = dict(table)
    while True:
        try:
            return TranslatorConfig(**kwargs)
        except TranslatorConfigError as e:
            reason = str(e).removeprefix(f"{e.key}: ")
            issues.add(f"translator.{e.key}", f"{reason}; using the default")
            del kwargs[e.key]


def build_config(data: object, *, source: Path) -> tuple[AppConfig, list[ConfigIssue]]:
    issues = _Issues(source)
    if not isinstance(data, Mapping):
        issues.add("", f"the file must hold TOML tables, got {type(data).__name__}; using defaults")
        return AppConfig(), issues.items
    for name in data:
        if name not in KNOWN_KEYS:
            _unknown(issues, str(name), name, tuple(KNOWN_KEYS), "section")
    hotkeys = _hotkeys(_section(data, "hotkeys", issues), issues)
    save_dir = _save_dir(_section(data, "capture", issues), issues)
    ocr = _ocr(_section(data, "ocr", issues), issues, source)
    postprocess, replacements = _postprocess(_section(data, "postprocess", issues), issues)
    show_text = _bool(_section(data, "notify", issues), "notify", "show_text", AppConfig.show_text, issues)
    debug = _bool(_section(data, "debug", issues), "debug", "enabled", AppConfig.debug, issues)
    translator = _translator(_section(data, "translator", issues), issues)
    config = AppConfig(hotkeys, ocr, postprocess, replacements, translator, show_text, debug, save_dir)
    return config, issues.items
