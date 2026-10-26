"""The user-facing commands that hotkeys and the tray menu trigger. Stdlib only."""

from __future__ import annotations

from enum import Enum


class Command(Enum):
    """Declaration order is significant: it fixes the hotkey ids (see ``hotkeys.hotkey_id``)."""

    CAPTURE = "capture"
    OCR = "ocr"
    TRANSLATE = "translate"
    LAST_RESULT = "last_result"
    OPEN_CONFIG = "open_config"
    QUIT = "quit"
    SETTINGS = "settings"  # M3: added last so the existing ids stay
