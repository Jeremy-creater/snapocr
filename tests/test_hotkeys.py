"""M2 WI-1: hotkey string parsing and formatting (PRD F5-2)."""

import ast
import sys
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from snapocr.hotkeys import (
    MOD_ALT,
    MOD_CONTROL,
    MOD_NOREPEAT,
    MOD_SHIFT,
    MOD_WIN,
    Hotkey,
    HotkeyError,
    format_hotkey,
    parse_hotkey,
)

MOD_NAMES = {"Ctrl": MOD_CONTROL, "Alt": MOD_ALT, "Shift": MOD_SHIFT, "Win": MOD_WIN}
# Win32 virtual-key codes, written out independently of the module under test.
KEYS = {
    **{chr(c): c for c in range(ord("A"), ord("Z") + 1)},
    **{str(d): 0x30 + d for d in range(10)},
    **{f"F{n}": 0x6F + n for n in range(1, 25)},
    "Space": 0x20, "Tab": 0x09, "Insert": 0x2D, "Delete": 0x2E,
    "Home": 0x24, "End": 0x23, "PageUp": 0x21, "PageDown": 0x22,
    "Left": 0x25, "Up": 0x26, "Right": 0x27, "Down": 0x28, "PrintScreen": 0x2C,
}


def test_win32_constants():
    assert (MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT) == (0x1, 0x2, 0x4, 0x8, 0x4000)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Alt+1", Hotkey(MOD_ALT, 0x31)),
        ("ctrl + shift + q", Hotkey(MOD_CONTROL | MOD_SHIFT, 0x51)),
        ("Ctrl+Alt+Shift+F24", Hotkey(MOD_CONTROL | MOD_ALT | MOD_SHIFT, 0x87)),
        ("Control+F1", Hotkey(MOD_CONTROL, 0x70)),
        ("Win+X", Hotkey(MOD_WIN, 0x58)),
        ("alt+a", Hotkey(MOD_ALT, 0x41)),
        ("  Alt+0  ", Hotkey(MOD_ALT, 0x30)),
        ("Alt+9", Hotkey(MOD_ALT, 0x39)),
        ("Shift+PrintScreen", Hotkey(MOD_SHIFT, 0x2C)),
        ("ALT+PAGEDOWN", Hotkey(MOD_ALT, 0x22)),
    ],
)
def test_parse_examples(text, expected):
    assert parse_hotkey(text) == expected


def test_default_hotkeys_parse():
    assert [parse_hotkey(f"Alt+{n}") for n in "1234"] == [
        Hotkey(MOD_ALT, 0x30 + n) for n in range(1, 5)
    ]


@pytest.mark.parametrize(("name", "vk"), sorted(KEYS.items()))
def test_every_main_key(name, vk):
    assert parse_hotkey(f"Ctrl+{name}") == Hotkey(MOD_CONTROL, vk)
    assert format_hotkey(Hotkey(MOD_CONTROL, vk)) == f"Ctrl+{name}"


@pytest.mark.parametrize(
    ("text", "token"),
    [
        ("", ""),
        ("   ", ""),
        ("Alt++1", ""),
        ("Alt+1+", ""),
        ("+Alt+1", ""),
        ("Alt+Alt+1", "Alt"),
        ("Ctrl+Control+1", "Control"),
        ("Alt+1+2", "2"),
        ("Alt+Shift", "Alt+Shift"),
        ("Alt", "Alt"),
        ("1", "1"),
        ("F5", "F5"),
        ("Alt+Foo", "Foo"),
        ("Alt+F25", "F25"),
        ("Alt+F0", "F0"),
        ("Alt+10", "10"),
        ("Alt+-", "-"),
        ("Alt+K", "K"),  # KELVIN SIGN lowercases to ASCII "k"
        ("Alt+Ａ", "Ａ"),  # fullwidth A
        ("Ａlt+1", "Ａlt"),
        ("Alt+١", "١"),  # Arabic-Indic digit one
        ("Alt+1\x00", "1\x00"),
    ],
)
def test_invalid_reports_token(text, token):
    with pytest.raises(HotkeyError) as info:
        parse_hotkey(text)
    assert info.value.token == token
    assert info.value.reason
    assert repr(token) in str(info.value)


@pytest.mark.parametrize("value", [None, 1, b"Alt+1", ["Alt", "1"]])
def test_non_str_rejected(value):
    with pytest.raises(HotkeyError) as info:
        parse_hotkey(value)
    assert info.value.token == ""


@pytest.mark.parametrize(
    ("mods", "vk"),
    [(0, 0x41), (0x10, 0x41), (MOD_ALT | MOD_NOREPEAT, 0x41), (MOD_ALT, 0x07), (MOD_ALT, 0x88),
     (True, 0x41), (MOD_ALT, True), (1.0, 0x41)],
)
def test_hotkey_rejects_invalid_values(mods, vk):
    with pytest.raises(ValueError):
        Hotkey(mods, vk)


def test_hotkey_is_frozen_and_hashable():
    h = Hotkey(MOD_ALT, 0x31)
    with pytest.raises(AttributeError):
        h.vk = 0x32
    assert {h: 1}[Hotkey(MOD_ALT, 0x31)] == 1


def test_format_canonical_order():
    h = Hotkey(MOD_WIN | MOD_SHIFT | MOD_ALT | MOD_CONTROL, 0x51)
    assert format_hotkey(h) == "Ctrl+Alt+Shift+Win+Q"
    assert format_hotkey(parse_hotkey("win+shift+alt+ctrl+q")) == "Ctrl+Alt+Shift+Win+Q"


# --- properties ------------------------------------------------------------------

hotkeys = st.builds(
    Hotkey,
    st.integers(1, 0xF),
    st.sampled_from(sorted(KEYS.values())),
)


@given(hotkeys)
def test_roundtrip(h):
    assert parse_hotkey(format_hotkey(h)) == h


@given(
    st.lists(st.sampled_from(["Ctrl", "Control", "Alt", "Shift", "Win"]), min_size=1, max_size=4, unique=True)
    .filter(lambda ms: not {"Ctrl", "Control"} <= set(ms)),
    st.sampled_from(sorted(KEYS)),
    st.randoms(use_true_random=False),
    st.lists(st.sampled_from(["", " ", "  ", "\t"]), min_size=10, max_size=10),
)
def test_order_case_whitespace_invariant(mods, key, rnd, pads):
    expected = sum({"Control": MOD_CONTROL, **MOD_NAMES}[m] for m in mods)
    shuffled = list(mods)
    rnd.shuffle(shuffled)
    tokens = [*shuffled, key]
    tokens = ["".join(c.upper() if rnd.random() < 0.5 else c.lower() for c in t) for t in tokens]
    text = "+".join(f"{pads[i]}{t}{pads[-1 - i]}" for i, t in enumerate(tokens))
    h = parse_hotkey(text)
    assert h == Hotkey(expected, KEYS[key])
    assert format_hotkey(parse_hotkey(format_hotkey(h))) == format_hotkey(h)


@given(st.text(alphabet=st.sampled_from(list("+ aAltCcrSshiWwnF12xK\t")) | st.characters(), max_size=20))
def test_total(text):
    try:
        h = parse_hotkey(text)
    except HotkeyError as e:
        assert isinstance(e.token, str)
    else:
        assert isinstance(h, Hotkey)
        assert parse_hotkey(format_hotkey(h)) == h


def test_module_uses_stdlib_only():
    import snapocr.hotkeys as mod

    tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
    imported = {
        (n.module if isinstance(n, ast.ImportFrom) else a.name).split(".")[0]
        for n in ast.walk(tree)
        if isinstance(n, (ast.Import, ast.ImportFrom)) and not (isinstance(n, ast.ImportFrom) and n.level)
        for a in (n.names if isinstance(n, ast.Import) else [n])
    }
    assert imported - {"snapocr"} <= sys.stdlib_module_names
    assert "ctypes" not in imported
