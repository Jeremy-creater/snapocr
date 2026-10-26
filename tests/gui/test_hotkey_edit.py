"""M3 WI-4: the hotkey recorder field (PRD F11-2; M3 plan D6). Offscreen, real key events.

Pinned here (beyond the plan text):
- Shows the hotkey in canonical form ("Alt+Q"); empty when there is none.
- A press of a non-modifier key with at least one modifier records it and
  emits ``hotkey_changed``. Holding only modifiers shows "Ctrl+Alt+…"; when
  the last modifier is released (or focus leaves) the value is shown again.
- Rejected (``rejected`` with a Chinese reason, value unchanged, no
  ``hotkey_changed``): no modifier, unsupported key, a keypad key.
- Esc without modifiers keeps the value and leaves the field.
- ``nativeVirtualKey`` wins when it is not 0; otherwise the Qt key is mapped.
- ShortcutOverride is accepted and Tab is recorded, not used to move focus.
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QLineEdit, QVBoxLayout, QWidget

from snapocr.gui.hotkey_edit import HotkeyEdit
from snapocr.hotkeys import MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, Hotkey, parse_hotkey

M = Qt.KeyboardModifier
K = Qt.Key
NONE = M.NoModifier


def send(widget, kind, key, mods=NONE, native_vk=0):
    event = QKeyEvent(kind, key, mods, 0, native_vk, 0)
    QApplication.sendEvent(widget, event)
    return event


def press(widget, key, mods=NONE, native_vk=0):
    send(widget, QEvent.Type.KeyPress, key, mods, native_vk)
    send(widget, QEvent.Type.KeyRelease, key, mods, native_vk)


class Recorder:
    def __init__(self, edit):
        self.changed, self.rejected = [], []
        edit.hotkey_changed.connect(self.changed.append)
        edit.rejected.connect(self.rejected.append)


@pytest.fixture
def edit(qtbot):
    host = QWidget()
    layout = QVBoxLayout(host)
    field = HotkeyEdit()
    other = QLineEdit()
    layout.addWidget(field)
    layout.addWidget(other)
    qtbot.addWidget(host)
    host.show()
    qtbot.waitExposed(host)
    field.set_hotkey(parse_hotkey("Alt+1"))
    field.setFocus()
    qtbot.waitUntil(field.hasFocus)
    field.other = other
    field.host = host  # keeps the parent (and so the field) alive
    return field


def test_shows_value_and_none(qtbot):
    field = HotkeyEdit()
    qtbot.addWidget(field)
    assert field.hotkey() is None
    assert field.text() == ""
    field.set_hotkey(parse_hotkey("ctrl+shift+q"))
    assert field.text() == "Ctrl+Shift+Q"
    field.set_hotkey(None)
    assert (field.hotkey(), field.text()) == (None, "")


def test_records_alt_q(edit):
    rec = Recorder(edit)
    press(edit, K.Key_Q, M.AltModifier)
    assert edit.hotkey() == Hotkey(MOD_ALT, 0x51)
    assert edit.text() == "Alt+Q"
    assert rec.changed == [Hotkey(MOD_ALT, 0x51)]
    assert rec.rejected == []


@pytest.mark.parametrize(
    ("key", "mods", "expected"),
    [
        (K.Key_F5, M.ControlModifier | M.ShiftModifier, "Ctrl+Shift+F5"),
        (K.Key_T, M.MetaModifier, "Win+T"),
        (K.Key_F24, M.ControlModifier | M.AltModifier | M.ShiftModifier | M.MetaModifier, "Ctrl+Alt+Shift+Win+F24"),
        (K.Key_Space, M.ControlModifier, "Ctrl+Space"),
        (K.Key_Print, M.AltModifier, "Alt+PrintScreen"),
        (K.Key_PageDown, M.ControlModifier, "Ctrl+PageDown"),
        (K.Key_Tab, M.ControlModifier, "Ctrl+Tab"),
        (K.Key_Backtab, M.ShiftModifier, "Shift+Tab"),
        (K.Key_9, M.AltModifier, "Alt+9"),
    ],
)
def test_qt_key_mapping(edit, key, mods, expected):
    press(edit, key, mods)
    assert edit.text() == expected
    assert edit.hotkey() == parse_hotkey(expected)


def test_native_virtual_key_wins(edit):
    # Shift+1 on a US layout: Qt reports "!", Windows reports VK '1'.
    press(edit, K.Key_Exclam, M.ShiftModifier, native_vk=0x31)
    assert edit.hotkey() == Hotkey(MOD_SHIFT, 0x31)


@pytest.mark.parametrize(
    ("key", "mods", "native_vk"),
    [
        (K.Key_1, M.ControlModifier, 0x61),  # numpad 1 on the real desktop
        (K.Key_1, M.ControlModifier | M.KeypadModifier, 0),  # numpad 1 offscreen
        (K.Key_Semicolon, M.ControlModifier, 0),
        (K.Key_Escape, M.ControlModifier, 0),
        (K.Key_Q, M.ControlModifier, 0xBA),  # a native code snapocr does not support
    ],
)
def test_unsupported_keys_rejected(edit, key, mods, native_vk):
    rec = Recorder(edit)
    press(edit, key, mods, native_vk)
    assert edit.hotkey() == parse_hotkey("Alt+1")
    assert edit.text() == "Alt+1"
    assert rec.changed == []
    assert len(rec.rejected) == 1
    assert "不支持" in rec.rejected[0]


@pytest.mark.parametrize("key", [K.Key_Q, K.Key_F1, K.Key_Tab, K.Key_Delete])
def test_no_modifier_rejected(edit, key):
    rec = Recorder(edit)
    press(edit, key)
    assert (edit.hotkey(), edit.text()) == (parse_hotkey("Alt+1"), "Alt+1")
    assert rec.changed == []
    assert len(rec.rejected) == 1
    assert all(name in rec.rejected[0] for name in ("Ctrl", "Alt", "Shift", "Win"))
    assert edit.hasFocus()  # Tab did not move focus


def test_modifier_preview_and_restore(edit):
    send(edit, QEvent.Type.KeyPress, K.Key_Control, M.ControlModifier)
    assert edit.text() == "Ctrl+…"
    send(edit, QEvent.Type.KeyPress, K.Key_Alt, M.ControlModifier | M.AltModifier)
    assert edit.text() == "Ctrl+Alt+…"
    send(edit, QEvent.Type.KeyRelease, K.Key_Alt, M.ControlModifier)
    assert edit.text() == "Ctrl+…"
    send(edit, QEvent.Type.KeyRelease, K.Key_Control, NONE)
    assert edit.text() == "Alt+1"
    assert edit.hotkey() == parse_hotkey("Alt+1")


def test_preview_then_main_key(edit):
    send(edit, QEvent.Type.KeyPress, K.Key_Shift, M.ShiftModifier)
    send(edit, QEvent.Type.KeyPress, K.Key_Meta, M.ShiftModifier | M.MetaModifier)
    assert edit.text() == "Shift+Win+…"
    press(edit, K.Key_S, M.ShiftModifier | M.MetaModifier)
    assert edit.text() == "Shift+Win+S"
    send(edit, QEvent.Type.KeyRelease, K.Key_Meta, M.ShiftModifier)
    send(edit, QEvent.Type.KeyRelease, K.Key_Shift, NONE)
    assert edit.text() == "Shift+Win+S"


def test_focus_out_restores(edit, qtbot):
    send(edit, QEvent.Type.KeyPress, K.Key_Control, M.ControlModifier)
    edit.other.setFocus()
    qtbot.waitUntil(lambda: not edit.hasFocus())
    assert edit.text() == "Alt+1"


def test_escape_keeps_value_and_leaves(edit, qtbot):
    rec = Recorder(edit)
    send(edit, QEvent.Type.KeyPress, K.Key_Alt, M.AltModifier)
    send(edit, QEvent.Type.KeyRelease, K.Key_Alt, NONE)
    press(edit, K.Key_Escape)
    qtbot.waitUntil(lambda: not edit.hasFocus())
    assert (edit.hotkey(), edit.text()) == (parse_hotkey("Alt+1"), "Alt+1")
    assert rec.changed == rec.rejected == []


def test_shortcut_override_accepted(edit):
    event = QKeyEvent(QEvent.Type.ShortcutOverride, K.Key_Q, M.AltModifier)
    event.ignore()
    QApplication.sendEvent(edit, event)
    assert event.isAccepted()


def test_typing_does_not_insert_text(edit):
    press(edit, K.Key_Q, M.AltModifier)
    QApplication.sendEvent(edit, QKeyEvent(QEvent.Type.KeyPress, K.Key_A, NONE, "a"))
    assert edit.text() == "Alt+Q"


def test_other_events_still_work(edit):
    edit.setEnabled(False)
    assert not edit.isEnabled()
    edit.setEnabled(True)
    assert edit.isEnabled()


_LETTERS = [(getattr(K, f"Key_{c}"), c) for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"]
_FKEYS = [(getattr(K, f"Key_F{n}"), f"F{n}") for n in range(1, 25)]
_NAMED = [
    (K.Key_Space, "Space"), (K.Key_Tab, "Tab"), (K.Key_Insert, "Insert"), (K.Key_Delete, "Delete"),
    (K.Key_Home, "Home"), (K.Key_End, "End"), (K.Key_PageUp, "PageUp"), (K.Key_PageDown, "PageDown"),
    (K.Key_Left, "Left"), (K.Key_Up, "Up"), (K.Key_Right, "Right"), (K.Key_Down, "Down"),
    (K.Key_Print, "PrintScreen"),
]
_MODS = [(M.ControlModifier, MOD_CONTROL), (M.AltModifier, MOD_ALT), (M.ShiftModifier, MOD_SHIFT),
         (M.MetaModifier, MOD_WIN)]


@given(st.sampled_from(_LETTERS + _FKEYS + _NAMED), st.sets(st.sampled_from(range(4)), min_size=1))
def test_every_supported_key_with_any_modifiers(qapp, key_name, mod_ids):
    key, name = key_name
    field = HotkeyEdit()
    qt_mods, win_mods = NONE, 0
    for i in mod_ids:
        qt_mods |= _MODS[i][0]
        win_mods |= _MODS[i][1]
    press(field, key, qt_mods)
    assert field.hotkey() == Hotkey(win_mods, parse_hotkey(f"Ctrl+{name}").vk)
    field.deleteLater()
