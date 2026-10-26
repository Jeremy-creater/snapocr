"""The values the settings window edits, their checks and their file changes (PRD F11). Stdlib only.

Only the items of M3 plan D4 are here; everything else in ``AppConfig`` is
left to the config file. ``changes`` gives what ``config.writer`` writes:
"section.key" -> TOML value, in ``KNOWN_KEYS`` order.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from snapocr.commands import Command
from snapocr.config.schema import HOTKEY_COMMANDS, KNOWN_KEYS, AppConfig
from snapocr.hotkeys import Hotkey, format_hotkey
from snapocr.translators.config import TranslatorConfig
from snapocr.translators.errors import TranslatorConfigError

TARGET_LANGS = ("auto", "zh", "en")
_SWITCHES = ("paragraphs", "spacing", "punctuation")
_TRANSLATOR_KEYS = ("model", "target_lang")


@dataclass(frozen=True)
class Settings:
    """A hotkey missing from ``hotkeys`` is disabled."""

    hotkeys: Mapping[Command, Hotkey]
    paragraphs: bool
    spacing: bool
    punctuation: bool
    target_lang: str
    model: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "hotkeys", MappingProxyType(dict(self.hotkeys)))


@dataclass(frozen=True)
class DuplicateHotkey:
    first: Command
    second: Command
    hotkey: Hotkey


@dataclass(frozen=True)
class BadModel:
    reason: str


@dataclass(frozen=True)
class BadTargetLang:
    value: object


Problem = DuplicateHotkey | BadModel | BadTargetLang


def settings_of(config: AppConfig) -> Settings:
    pp = config.postprocess
    tr = config.translator
    return Settings(config.hotkeys, pp.paragraphs, pp.spacing, pp.punctuation, tr.target_lang, tr.model)


def check(s: Settings) -> list[Problem]:
    problems: list[Problem] = []
    bound = [c for c in HOTKEY_COMMANDS if c in s.hotkeys]
    for i, first in enumerate(bound):
        for second in bound[i + 1:]:
            if s.hotkeys[first] == s.hotkeys[second]:
                problems.append(DuplicateHotkey(first, second, s.hotkeys[first]))
    try:
        TranslatorConfig(model=s.model)
    except TranslatorConfigError as e:
        problems.append(BadModel(str(e).removeprefix(f"{e.key}: ")))
    if not isinstance(s.target_lang, str) or s.target_lang not in TARGET_LANGS:
        problems.append(BadTargetLang(s.target_lang))
    return problems


def _values(s: Settings) -> dict[str, bool | str]:
    out: dict[str, bool | str] = {f"hotkeys.{c.value}": format_hotkey(h) for c, h in s.hotkeys.items()}
    out |= {f"postprocess.{name}": getattr(s, name) for name in _SWITCHES}
    out |= {f"translator.{name}": getattr(s, name) for name in _TRANSLATOR_KEYS}
    return out


def changes(old: Settings, new: Settings) -> dict[str, bool | str]:
    before, after = _values(old), _values(new)
    order = [f"{section}.{key}" for section, keys in KNOWN_KEYS.items() for key in keys]
    return {k: after[k] for k in order if k in after and before.get(k) != after[k]}


def apply(config: AppConfig, s: Settings) -> AppConfig:
    """``config`` with the window's items replaced; ValueError if ``check(s)`` finds problems."""
    problems = check(s)
    if problems:
        raise ValueError(f"settings have problems: {problems}")
    return dataclasses.replace(
        config,
        hotkeys=s.hotkeys,
        postprocess=dataclasses.replace(config.postprocess, **{name: getattr(s, name) for name in _SWITCHES}),
        translator=dataclasses.replace(config.translator, model=s.model, target_lang=s.target_lang),
    )
