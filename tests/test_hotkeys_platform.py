"""M9 WI-5: hotkey strings by platform (PRD F23-2; M9 plan D9).

Pinned here (beyond the plan text):
- ``platform`` is keyword-only, default ``"win32"``; an unknown platform is a
  ``ValueError`` (not a ``HotkeyError``), from parse and format alike.
- ``Option`` is ``Alt`` on both platforms and is written back as ``Alt``.
- ``Cmd`` / ``Command`` are the Win bit on darwin; on win32 they are an error
  whose reason names macOS. ``Win`` on darwin is an error whose reason names
  macOS and Cmd.
- On darwin ``Insert``, ``PrintScreen`` and ``F21``-``F24`` are errors naming
  the key: a Mac keyboard has no such key.
- The missing-modifier reason lists the platform's modifier names.
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from snapocr.hotkeys import (
    MOD_ALT,
    MOD_CMD,
    MOD_CONTROL,
    MOD_SHIFT,
    MOD_WIN,
    Hotkey,
    HotkeyError,
    format_hotkey,
    parse_hotkey,
)

# Win32 virtual-key codes, written out independently of the module under test.
KEYS = {
    **{chr(c): c for c in range(ord("A"), ord("Z") + 1)},
    **{str(d): 0x30 + d for d in range(10)},
    **{f"F{n}": 0x6F + n for n in range(1, 25)},
    "Space": 0x20, "Tab": 0x09, "Insert": 0x2D, "Delete": 0x2E,
    "Home": 0x24, "End": 0x23, "PageUp": 0x21, "PageDown": 0x22,
    "Left": 0x25, "Up": 0x26, "Right": 0x27, "Down": 0x28, "PrintScreen": 0x2C,
}
NOT_ON_A_MAC = {"Insert", "PrintScreen", "F21", "F22", "F23", "F24"}
MAC_KEYS = {k: v for k, v in KEYS.items() if k not in NOT_ON_A_MAC}
VALID = {"win32": KEYS, "darwin": MAC_KEYS}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Option+1", Hotkey(MOD_ALT, 0x31)),
        ("option + shift + q", Hotkey(MOD_ALT | MOD_SHIFT, 0x51)),
        ("Cmd+Shift+S", Hotkey(MOD_CMD | MOD_SHIFT, 0x53)),
        ("Command+S", Hotkey(MOD_CMD, 0x53)),
        ("  COMMAND + ctrl + F20 ", Hotkey(MOD_CMD | MOD_CONTROL, 0x83)),
        ("Ctrl+Option+Shift+F19", Hotkey(MOD_CONTROL | MOD_ALT | MOD_SHIFT, 0x82)),
        ("Control+Delete", Hotkey(MOD_CONTROL, 0x2E)),
        ("Alt+1", Hotkey(MOD_ALT, 0x31)),
    ],
)
def test_mac_examples(text, expected):
    assert parse_hotkey(text, platform="darwin") == expected


def test_option_is_alt_on_windows_too():
    assert parse_hotkey("Option+1") == parse_hotkey("Alt+1") == Hotkey(MOD_ALT, 0x31)
    assert parse_hotkey("Option+1", platform="win32") == Hotkey(MOD_ALT, 0x31)


@pytest.mark.parametrize(
    ("platform", "text", "token", "says"),
    [
        ("darwin", "Win+X", "Win", "macOS"),
        ("darwin", "Alt+win+1", "win", "Cmd"),
        ("darwin", "Ctrl+Insert", "Insert", "Mac"),
        ("darwin", "Shift+PrintScreen", "PrintScreen", "Mac"),
        ("darwin", "Alt+F21", "F21", "Mac"),
        ("darwin", "Alt+f24", "f24", "Mac"),
        ("darwin", "Option+Alt+1", "Alt", "twice"),
        ("darwin", "Cmd+Command+1", "Command", "twice"),
        ("win32", "Cmd+1", "Cmd", "macOS"),
        ("win32", "Command+Shift+S", "Command", "Win"),
        ("win32", "Alt+Option+1", "Option", "twice"),
    ],
)
def test_wrong_platform_names_report_the_token(platform, text, token, says):
    with pytest.raises(HotkeyError) as info:
        parse_hotkey(text, platform=platform)
    assert info.value.token == token
    assert says in info.value.reason


def test_missing_modifier_names_the_platforms_modifiers():
    with pytest.raises(HotkeyError) as info:
        parse_hotkey("Q", platform="darwin")
    assert "(Ctrl, Option, Shift, Cmd)" in info.value.reason
    with pytest.raises(HotkeyError) as info:
        parse_hotkey("Q", platform="win32")
    assert "(Ctrl, Alt, Shift, Win)" in info.value.reason


def test_format_by_platform():
    h = Hotkey(MOD_WIN | MOD_SHIFT | MOD_ALT | MOD_CONTROL, 0x51)
    assert format_hotkey(h) == "Ctrl+Alt+Shift+Win+Q"
    assert format_hotkey(h, platform="win32") == "Ctrl+Alt+Shift+Win+Q"
    assert format_hotkey(h, platform="darwin") == "Ctrl+Alt+Shift+Cmd+Q"
    assert format_hotkey(parse_hotkey("Option+1", platform="darwin"), platform="darwin") == "Alt+1"


@pytest.mark.parametrize("call", [lambda: parse_hotkey("Alt+1", platform="linux"),
                                  lambda: format_hotkey(Hotkey(MOD_ALT, 0x31), platform="linux")])
def test_unknown_platform(call):
    with pytest.raises(ValueError, match="linux") as info:
        call()
    assert not isinstance(info.value, HotkeyError)


# --- properties ------------------------------------------------------------------


@st.composite
def platform_hotkeys(draw):
    platform = draw(st.sampled_from(["win32", "darwin"]))
    return platform, Hotkey(draw(st.integers(1, 0xF)), draw(st.sampled_from(sorted(VALID[platform].values()))))


@given(platform_hotkeys())
def test_roundtrip_per_platform(ph):
    platform, h = ph
    assert parse_hotkey(format_hotkey(h, platform=platform), platform=platform) == h


@given(st.sampled_from(["win32", "darwin"]), st.integers(1, 0xF), st.sampled_from(sorted(MAC_KEYS)),
       st.sampled_from(["Option", "option", "OPTION"]))
def test_alt_and_option_are_the_same(platform, mods, key, option):
    names = [n for n, bit in (("Ctrl", MOD_CONTROL), ("Alt", MOD_ALT), ("Shift", MOD_SHIFT)) if mods & bit]
    if mods & MOD_WIN:
        names.append("Win" if platform == "win32" else "Cmd")
    text = "+".join([*names, key])
    assert parse_hotkey(text.replace("Alt", option), platform=platform) == parse_hotkey(text, platform=platform)


@given(st.integers(1, 0x7), st.sampled_from(sorted(MAC_KEYS.values())))
def test_one_config_text_for_both_systems(mods, vk):
    """Without the Win / Cmd bit and with a key both keyboards have, the config text is the same."""
    h = Hotkey(mods, vk)
    assert format_hotkey(h, platform="darwin") == format_hotkey(h, platform="win32")
    assert parse_hotkey(format_hotkey(h), platform="darwin") == h
