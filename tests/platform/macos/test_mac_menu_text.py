"""M9 WI-7: Qt on a Mac reads the menu's hotkey text as the true keys (PRD F23-2).

A native Mac menu parses the text after the tab as a key sequence and draws it
in the shortcut column (measured 2026-10-30: "Alt+1" drew ⌥1, "Ctrl+Alt+Q"
drew ⌥⌘Q because Qt swaps Control and Command). So the text must be one Qt
reads back as the hotkey's own keys: ⌃ is Qt's Meta, ⌘ is Qt's Control.
This needs Qt's macOS key names, so it runs on a Mac only (unit lane there).
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st
from PySide6.QtCore import QKeyCombination, Qt
from PySide6.QtGui import QKeySequence

from snapocr.hotkeys import MOD_ALT, MOD_CMD, MOD_CONTROL, MOD_SHIFT, Hotkey, display_hotkey
from test_hotkeys_platform import KEYS, MAC_KEYS

pytestmark = pytest.mark.macos

M = Qt.KeyboardModifier
QT_MODS = ((MOD_CONTROL, M.MetaModifier), (MOD_ALT, M.AltModifier), (MOD_SHIFT, M.ShiftModifier),
           (MOD_CMD, M.ControlModifier))
QT_KEY_NAMES = {"PageUp": "Key_PageUp", "PageDown": "Key_PageDown"}


@given(st.integers(1, 0xF), st.sampled_from(sorted(MAC_KEYS)))
def test_qt_reads_the_menu_text_as_the_hotkey(mods, key):
    shown = display_hotkey(Hotkey(mods, KEYS[key]), platform="darwin")
    seq = QKeySequence.fromString(shown, QKeySequence.SequenceFormat.NativeText)
    qt_mods = M.NoModifier
    for bit, flag in QT_MODS:
        if mods & bit:
            qt_mods |= flag
    qt_key = getattr(Qt.Key, QT_KEY_NAMES.get(key, f"Key_{key}"))
    assert seq.count() == 1, shown
    assert seq[0] == QKeyCombination(qt_mods, qt_key), shown
