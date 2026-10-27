"""The configuration value (``AppConfig``), its known keys and ``ConfigIssue``. Stdlib only."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType

from snapocr.commands import Command
from snapocr.engines.config import OcrEngineConfig
from snapocr.hotkeys import Hotkey, parse_hotkey
from snapocr.postprocess import PostprocessOptions, Replacements
from snapocr.translators.config import TranslatorConfig

HOTKEY_COMMANDS = (Command.CAPTURE, Command.OCR, Command.TRANSLATE, Command.LAST_RESULT)
DEFAULT_HOTKEY_TEXT: Mapping[Command, str] = MappingProxyType(
    {c: f"Alt+{n}" for n, c in enumerate(HOTKEY_COMMANDS, 1)}
)
DEFAULT_HOTKEYS: Mapping[Command, Hotkey] = MappingProxyType(
    {c: parse_hotkey(t) for c, t in DEFAULT_HOTKEY_TEXT.items()}
)

# Section -> keys, in the order the template lists them (WI-7 checks the template against this).
KNOWN_KEYS: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "hotkeys": tuple(c.value for c in HOTKEY_COMMANDS),
        "ocr": ("min_score", "model_dir"),
        "postprocess": ("paragraphs", "spacing", "punctuation", "replacements"),
        "notify": ("show_text",),
        "translator": (
            "base_url",
            "model",
            "timeout_s",
            "target_lang",
            "direction_threshold",
            "prompt_template",
            "max_input_chars",
            "sampling",
        ),
    }
)


@dataclass(frozen=True)
class AppConfig:
    """A hotkey left out of ``hotkeys`` is disabled."""

    hotkeys: Mapping[Command, Hotkey] = DEFAULT_HOTKEYS
    ocr: OcrEngineConfig = field(default_factory=OcrEngineConfig)
    postprocess: PostprocessOptions = field(default_factory=PostprocessOptions)
    replacements: Replacements = Replacements.EMPTY
    translator: TranslatorConfig = field(default_factory=TranslatorConfig)
    show_text: bool = True  # [notify] show_text: OCR notices show the text (F7-2)


@dataclass(frozen=True)
class ConfigIssue:
    file: Path
    key_path: str
    reason: str

    def __str__(self) -> str:
        where = f"{self.file.name}: {self.key_path}" if self.key_path else self.file.name
        return f"{where}: {self.reason}"
