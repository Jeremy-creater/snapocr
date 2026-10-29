"""M9 WI-6 (plan D10): Mac key codes, Carbon modifiers, "taken" by platform (PRD F23-2).

Pinned here (beyond the plan text):
- ``mac_keycode`` returns None for a key a Mac keyboard does not have
  (Insert, PrintScreen, F21-F24) and for a code that is not a hotkey key;
  ``vk_from_mac_keycode`` likewise returns None for an unknown code.
- ``Delete`` (VK_DELETE, the forward delete) is kVK_ForwardDelete, not the
  Mac "delete" key (kVK_Delete, backspace).
- Every function here takes ``platform`` keyword-only, defaulting to win32;
  an unknown platform raises ValueError.
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from snapocr.actions.messages import hotkey_failed_notice, hotkey_failure_line
from snapocr.commands import Command
from snapocr.hotkeys import (
    MOD_ALT,
    MOD_CMD,
    MOD_CONTROL,
    MOD_NOREPEAT,
    MOD_SHIFT,
    MOD_WIN,
    HotkeyFailure,
    carbon_modifiers,
    hotkey_taken,
    mac_keycode,
    vk_from_mac_keycode,
)

# kVK_ANSI_* and the independent keys, copied from Carbon's Events.h (HIToolbox).
KVK = {
    "A": 0x00, "S": 0x01, "D": 0x02, "F": 0x03, "H": 0x04, "G": 0x05, "Z": 0x06, "X": 0x07,
    "C": 0x08, "V": 0x09, "B": 0x0B, "Q": 0x0C, "W": 0x0D, "E": 0x0E, "R": 0x0F, "Y": 0x10,
    "T": 0x11, "1": 0x12, "2": 0x13, "3": 0x14, "4": 0x15, "6": 0x16, "5": 0x17, "9": 0x19,
    "7": 0x1A, "8": 0x1C, "0": 0x1D, "O": 0x1F, "U": 0x20, "I": 0x22, "P": 0x23, "L": 0x25,
    "J": 0x26, "K": 0x28, "N": 0x2D, "M": 0x2E,
    "Tab": 0x30, "Space": 0x31, "Delete": 0x75, "Home": 0x73, "PageUp": 0x74, "End": 0x77,
    "PageDown": 0x79, "Left": 0x7B, "Right": 0x7C, "Down": 0x7D, "Up": 0x7E,
    "F1": 0x7A, "F2": 0x78, "F3": 0x63, "F4": 0x76, "F5": 0x60, "F6": 0x61, "F7": 0x62,
    "F8": 0x64, "F9": 0x65, "F10": 0x6D, "F11": 0x67, "F12": 0x6F, "F13": 0x69, "F14": 0x6B,
    "F15": 0x71, "F16": 0x6A, "F17": 0x40, "F18": 0x4F, "F19": 0x50, "F20": 0x5A,
}
# Win32 virtual-key codes, as in tests/test_hotkeys.py.
VK = {
    **{chr(c): c for c in range(ord("A"), ord("Z") + 1)},
    **{str(d): 0x30 + d for d in range(10)},
    **{f"F{n}": 0x6F + n for n in range(1, 25)},
    "Space": 0x20, "Tab": 0x09, "Insert": 0x2D, "Delete": 0x2E,
    "Home": 0x24, "End": 0x23, "PageUp": 0x21, "PageDown": 0x22,
    "Left": 0x25, "Up": 0x26, "Right": 0x27, "Down": 0x28, "PrintScreen": 0x2C,
}
NOT_ON_A_MAC = ["Insert", "PrintScreen", "F21", "F22", "F23", "F24"]
MAC_KEYS = sorted(set(VK) - set(NOT_ON_A_MAC))

# Carbon modifier bits (Events.h): cmdKey, shiftKey, optionKey, controlKey.
CARBON = {MOD_WIN: 0x0100, MOD_SHIFT: 0x0200, MOD_ALT: 0x0800, MOD_CONTROL: 0x1000}


def test_cmd_is_the_win_bit():
    assert MOD_CMD == MOD_WIN == 0x8


def test_kvk_table_covers_exactly_the_mac_keys():
    assert sorted(KVK) == MAC_KEYS


@pytest.mark.parametrize("name", MAC_KEYS)
def test_mac_keycode_matches_events_h(name):
    assert mac_keycode(VK[name]) == KVK[name]
    assert vk_from_mac_keycode(KVK[name]) == VK[name]


@pytest.mark.parametrize("name", NOT_ON_A_MAC)
def test_keys_a_mac_does_not_have(name):
    assert mac_keycode(VK[name]) is None


@pytest.mark.parametrize("code", [0x33, 0x35, 0x18, 0x7F, 0xFF, -1, 0x1000])
def test_unknown_mac_codes(code):
    """Backspace (0x33), Escape (0x35), "=" (0x18) and codes no key has."""
    assert vk_from_mac_keycode(code) is None


@pytest.mark.parametrize("vk", [0x00, 0x41 - 1, 0x1B, 0x90, 0xFFFF])
def test_mac_keycode_unknown_vk(vk):
    assert mac_keycode(vk) is None


def test_mac_keycode_is_injective():
    codes = [mac_keycode(VK[name]) for name in MAC_KEYS]
    assert len(set(codes)) == len(codes)


@given(st.sampled_from(MAC_KEYS))
def test_keycode_round_trip(name):
    assert vk_from_mac_keycode(mac_keycode(VK[name])) == VK[name]


# --- carbon_modifiers ----------------------------------------------------------------------

_mods = st.integers(1, 0xF)


@pytest.mark.parametrize(("mod", "bit"), list(CARBON.items()))
def test_carbon_single_modifiers(mod, bit):
    assert carbon_modifiers(mod) == bit


def test_carbon_modifiers_is_a_bijection_on_the_15_combinations():
    masks = {carbon_modifiers(m) for m in range(1, 16)}
    assert len(masks) == 15
    for m in range(1, 16):
        assert carbon_modifiers(m) == sum(bit for mod, bit in CARBON.items() if m & mod)


@given(_mods)
def test_carbon_ignores_norepeat(mods):
    assert carbon_modifiers(mods | MOD_NOREPEAT) == carbon_modifiers(mods)


@pytest.mark.parametrize("mods", [0, 0x10, -1])
def test_carbon_rejects_no_or_unknown_modifiers(mods):
    with pytest.raises(ValueError):
        carbon_modifiers(mods)


# --- taken by another program, by platform ----------------------------------------------------


@pytest.mark.parametrize(
    ("code", "platform", "taken"),
    [(1409, "win32", True), (87, "win32", False), (-9878, "win32", False),
     (-9878, "darwin", True), (1409, "darwin", False), (-50, "darwin", False)],
)
def test_hotkey_taken(code, platform, taken):
    assert hotkey_taken(code, platform=platform) is taken


def test_hotkey_taken_defaults_to_win32():
    assert hotkey_taken(1409) is True


@pytest.mark.parametrize("platform", ["linux", "", "Darwin"])
def test_hotkey_taken_unknown_platform(platform):
    with pytest.raises(ValueError, match="platform"):
        hotkey_taken(1409, platform=platform)


@pytest.mark.parametrize(
    ("code", "platform", "line"),
    [
        (1409, "win32", "Alt+2（OCR）：已被其他软件占用"),
        (87, "win32", "Alt+2（OCR）：注册失败，错误码 87"),
        (-9878, "darwin", "Alt+2（OCR）：已被其他软件占用"),
        (-50, "darwin", "Alt+2（OCR）：注册失败，错误码 -50"),
        (1409, "darwin", "Alt+2（OCR）：注册失败，错误码 1409"),
    ],
)
def test_failure_line_by_platform(code, platform, line):
    assert hotkey_failure_line(HotkeyFailure(Command.OCR, "Alt+2", code), platform=platform) == line


def test_failed_notice_by_platform():
    n = hotkey_failed_notice([HotkeyFailure(Command.OCR, "Alt+2", -9878)], platform="darwin")
    assert n.body.splitlines()[0] == "Alt+2（OCR）：已被其他软件占用"
