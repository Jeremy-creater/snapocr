"""The user-facing commands that hotkeys and the tray menu trigger. Stdlib only."""

from __future__ import annotations

from enum import Enum


class Command(Enum):
    """Declaration order is significant: it fixes the hotkey ids (see ``hotkeys.hotkey_id``)."""

    CAPTURE = "capture"
    OCR = "ocr"
    TRANSLATE = "translate"
    TRANSLATE_TEXT = "translate_text"  # M6 (F19-1): in the place of LAST_RESULT, so the id stays 4
    OPEN_CONFIG = "open_config"
    QUIT = "quit"
    SETTINGS = "settings"  # M3: added last so the existing ids stay
    CODE_OCR = "code_ocr"  # M3 WI-14 (F13-1): added last for the same reason
    TABLE_OCR = "table_ocr"  # M4 WI-15 (F16-1): added last for the same reason
