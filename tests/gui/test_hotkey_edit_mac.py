"""M9 WI-8: the hotkey recorder on a Mac (PRD F23-2, F11-2; M9 plan D9). Offscreen, real key events.

Measured on macOS 26 with PySide6 6.12 (2026-10-30, synthetic presses):
- Qt swaps the modifiers: the Control key arrives as ``MetaModifier``, the
  Command key as ``ControlModifier``. Option is ``AltModifier``.
- ``nativeVirtualKey()`` is the Carbon key code (kVK): ⌥1 is 0x12, ⌥Q 0x0C;
  for A it is 0, the same as "no native code", so 0 falls back to the Qt key.
- ⌥1 arrives as ``Key_1`` (text "¡"), ⇧1 as ``Key_Exclam``.

Pinned here (beyond the plan text):
- A non-zero native code wins over the Qt key; a code that is no hotkey key
  (a keypad key) is rejected, as are keys a Mac keyboard lacks (Insert, F21).
- Values and previews are shown as ⌃⌥⇧⌘ symbols; the reasons name the Mac keys.
- The Windows recorder (``platform`` left out) is pinned by test_hotkey_edit.py.
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from snapocr.gui.hotkey_edit import HotkeyEdit
from snapocr.gui.settings_window import SettingsWindow
from snapocr.commands import Command
from snapocr.hotkeys import MOD_ALT, MOD_CMD, MOD_CONTROL, MOD_SHIFT, Hotkey, parse_hotkey
from test_hotkeys_platform import KEYS, MAC_KEYS

M = Qt.KeyboardModifier
K = Qt.Key
NONE = M.NoModifier

# Carbon kVK codes (Events.h), written out independently of the module under test.
KVK = {
    "A": 0x00, "S": 0x01, "Q": 0x0C, "1": 0x12, "2": 0x13, "0": 0x1D, "F5": 0x60, "F20": 0x5A,
    "Left": 0x7B, "Keypad1": 0x53, "Escape": 0x35,
}


def press(widget, key, mods=NONE, native=0):
    for kind in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
        QApplication.sendEvent(widget, QKeyEvent(kind, key, mods, 0, native, 0))


def send(widget, kind, key, mods):
    QApplication.sendEvent(widget, QKeyEvent(kind, key, mods))


class Recorder:
    def __init__(self, edit):
        self.changed, self.rejected = [], []
        edit.hotkey_changed.connect(self.changed.append)
        edit.rejected.connect(self.rejected.append)


@pytest.fixture
def edit(qtbot):
    field = HotkeyEdit(platform="darwin")
    qtbot.addWidget(field)
    field.show()
    qtbot.waitExposed(field)
    field.set_hotkey(parse_hotkey("Alt+1"))
    field.setFocus()
    qtbot.waitUntil(field.hasFocus)
    return field


def test_shows_mac_symbols(edit):
    assert edit.text() == "⌥1"
    edit.set_hotkey(parse_hotkey("Ctrl+Shift+Cmd+Left", platform="darwin"))
    assert edit.text() == "⌃⇧⌘←"


@pytest.mark.parametrize(
    ("key", "mods", "native", "expected", "shown"),
    [
        (K.Key_2, M.AltModifier, KVK["2"], Hotkey(MOD_ALT, 0x32), "⌥2"),  # Option+2 as measured
        (K.Key_Exclam, M.ShiftModifier | M.AltModifier, KVK["1"], Hotkey(MOD_ALT | MOD_SHIFT, 0x31), "⌥⇧1"),
        (K.Key_S, M.ControlModifier, KVK["S"], Hotkey(MOD_CMD, 0x53), "⌘S"),  # the Command key
        (K.Key_A, M.MetaModifier, KVK["A"], Hotkey(MOD_CONTROL, 0x41), "⌃A"),  # the Control key; kVK 0
        (K.Key_F5, M.MetaModifier | M.AltModifier, KVK["F5"], Hotkey(MOD_CONTROL | MOD_ALT, 0x74), "⌃⌥F5"),
        (K.Key_Q, M.ControlModifier | M.ShiftModifier, 0, Hotkey(MOD_CMD | MOD_SHIFT, 0x51), "⇧⌘Q"),  # offscreen
    ],
)
def test_records_mac_presses(edit, key, mods, native, expected, shown):
    rec = Recorder(edit)
    press(edit, key, mods, native)
    assert (edit.hotkey(), edit.text()) == (expected, shown)
    assert (rec.changed, rec.rejected) == ([expected], [])


def test_a_mac_preview_uses_symbols_in_mac_order(edit):
    send(edit, QEvent.Type.KeyPress, K.Key_Control, M.ControlModifier)  # the Command key
    assert edit.text() == "⌘…"
    send(edit, QEvent.Type.KeyPress, K.Key_Meta, M.ControlModifier | M.MetaModifier)  # the Control key
    assert edit.text() == "⌃⌘…"
    send(edit, QEvent.Type.KeyPress, K.Key_Shift, M.ControlModifier | M.MetaModifier | M.ShiftModifier)
    send(edit, QEvent.Type.KeyPress, K.Key_Alt, M.ControlModifier | M.MetaModifier | M.ShiftModifier | M.AltModifier)
    assert edit.text() == "⌃⌥⇧⌘…"
    for key, left in ((K.Key_Alt, M.ControlModifier | M.MetaModifier | M.ShiftModifier),
                      (K.Key_Shift, M.ControlModifier | M.MetaModifier), (K.Key_Meta, M.ControlModifier),
                      (K.Key_Control, NONE)):
        send(edit, QEvent.Type.KeyRelease, key, left)
    assert edit.text() == "⌥1"


@pytest.mark.parametrize(
    ("key", "mods", "native"),
    [
        (K.Key_1, M.ControlModifier, KVK["Keypad1"]),
        (K.Key_Insert, M.MetaModifier, 0),  # no such key on a Mac
        (K.Key_F21, M.AltModifier, 0),
        (K.Key_Print, M.AltModifier, 0),
    ],
)
def test_keys_a_mac_cannot_use_are_rejected(edit, key, mods, native):
    rec = Recorder(edit)
    press(edit, key, mods, native)
    assert (edit.hotkey(), edit.text()) == (parse_hotkey("Alt+1"), "⌥1")
    assert rec.changed == []
    assert len(rec.rejected) == 1 and "不支持" in rec.rejected[0] and "F1–F20" in rec.rejected[0]


def test_no_modifier_names_the_mac_keys(edit):
    rec = Recorder(edit)
    press(edit, K.Key_Q, NONE, KVK["Q"])
    assert rec.changed == []
    assert len(rec.rejected) == 1
    assert all(name in rec.rejected[0] for name in ("Control", "Option", "Shift", "Command"))
    assert "Win" not in rec.rejected[0]


def test_escape_still_cancels(edit, qtbot):
    press(edit, K.Key_Escape, NONE, KVK["Escape"])
    qtbot.waitUntil(lambda: not edit.hasFocus())
    assert edit.text() == "⌥1"


@given(st.sampled_from(sorted(MAC_KEYS)))
def test_the_native_code_names_the_key(qapp, name):
    """Every Mac key records from its kVK code even when Qt names another key (S5, against WI-6's table)."""
    from snapocr.hotkeys import mac_keycode

    field = HotkeyEdit(platform="darwin")
    vk = KEYS[name]
    code = mac_keycode(vk)
    qt_key = K.Key_A if code == 0 else K.Key_Exclam  # kVK 0 is A, read from the Qt key
    press(field, qt_key, M.AltModifier, code)
    assert field.hotkey() == Hotkey(MOD_ALT, vk)
    field.deleteLater()


def test_the_settings_window_records_mac_keys(qtbot):
    window = SettingsWindow(platform="darwin")
    qtbot.addWidget(window)
    edit = window.hotkey_edits[Command.OCR]
    edit.set_hotkey(parse_hotkey("Alt+2"))
    assert edit.text() == "⌥2"
    press(edit, K.Key_A, NONE, KVK["A"])
    assert all(name in window.problems_label.text() for name in ("OCR", "Command"))
