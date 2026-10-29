"""M9 WI-7: hotkeys shown in the interface by platform (PRD F23-2; M9 plan D9).

Pinned here (beyond the plan text):
- ``display_hotkey`` on win32 is exactly ``format_hotkey``.
- On darwin the modifiers are the symbols ⌃⌥⇧⌘ in that order, with no
  separators, then the key: arrows, Tab, Delete, Home, End, PageUp and
  PageDown as their Mac symbols, every other key by its config name.
- ``register_all(..., platform=)`` and ``settings_problem_text(..., platform=)``
  write the hotkey that way, so a Mac never shows ``Win`` or ``Alt``.
- An unknown platform is a ``ValueError``.
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from snapocr.actions.messages import settings_problem_text
from snapocr.commands import Command
from snapocr.config.settings import DuplicateHotkey
from snapocr.hotkeys import (
    MOD_ALT,
    MOD_CMD,
    MOD_CONTROL,
    MOD_SHIFT,
    Hotkey,
    HotkeyFailure,
    display_hotkey,
    format_hotkey,
    parse_hotkey,
    register_all,
)
from test_hotkeys_platform import KEYS, MAC_KEYS

SYMBOLS = ((MOD_CONTROL, "⌃"), (MOD_ALT, "⌥"), (MOD_SHIFT, "⇧"), (MOD_CMD, "⌘"))
MAC_KEY_SYMBOLS = {"Left": "←", "Up": "↑", "Right": "→", "Down": "↓", "Tab": "⇥", "Delete": "⌦",
                   "Home": "↖", "End": "↘", "PageUp": "⇞", "PageDown": "⇟"}


@pytest.mark.parametrize(
    ("text", "shown"),
    [
        ("Alt+1", "⌥1"),
        ("Option+6", "⌥6"),
        ("Ctrl+Alt+Q", "⌃⌥Q"),
        ("Shift+Cmd+S", "⇧⌘S"),
        ("Cmd+Shift+Option+Ctrl+F19", "⌃⌥⇧⌘F19"),
        ("Ctrl+Left", "⌃←"),
        ("Alt+PageDown", "⌥⇟"),
        ("Cmd+Delete", "⌘⌦"),
        ("Ctrl+Space", "⌃Space"),
    ],
)
def test_mac_examples(text, shown):
    assert display_hotkey(parse_hotkey(text, platform="darwin"), platform="darwin") == shown


@pytest.mark.parametrize("text", ["Alt+1", "Ctrl+Alt+Shift+Win+F24", "Shift+Left", "Win+Insert"])
def test_windows_shows_the_config_text(text):
    hk = parse_hotkey(text)
    assert display_hotkey(hk) == display_hotkey(hk, platform="win32") == format_hotkey(hk) == text


def test_unknown_platform():
    with pytest.raises(ValueError, match="unknown platform"):
        display_hotkey(parse_hotkey("Alt+1"), platform="linux")


@given(st.integers(1, 0xF), st.sampled_from(sorted(MAC_KEYS)))
def test_mac_symbols_follow_the_bits(mods, key):
    shown = display_hotkey(Hotkey(mods, KEYS[key]), platform="darwin")
    prefix = "".join(symbol for bit, symbol in SYMBOLS if mods & bit)
    assert shown == prefix + MAC_KEY_SYMBOLS.get(key, key)
    for bit, symbol in SYMBOLS:
        assert shown.count(symbol) == (1 if mods & bit else 0)


def test_failures_are_shown_by_platform():
    bindings = {Command.CAPTURE: parse_hotkey("Shift+Cmd+S", platform="darwin"), Command.OCR: parse_hotkey("Alt+2")}
    report = register_all(bindings, lambda hid, mods, vk: -9878, platform="darwin")
    assert report.failed == [HotkeyFailure(Command.CAPTURE, "⇧⌘S", -9878), HotkeyFailure(Command.OCR, "⌥2", -9878)]
    report = register_all(bindings, lambda hid, mods, vk: 1409)
    assert [f.hotkey_text for f in report.failed] == ["Shift+Win+S", "Alt+2"]


def test_duplicate_hotkey_text_by_platform():
    p = DuplicateHotkey(Command.CAPTURE, Command.OCR, parse_hotkey("Ctrl+Cmd+1", platform="darwin"))
    assert settings_problem_text(p, platform="darwin") == "「截图」和「OCR」用了同一个热键 ⌃⌘1。"
    assert settings_problem_text(p) == "「截图」和「OCR」用了同一个热键 Ctrl+Win+1。"
