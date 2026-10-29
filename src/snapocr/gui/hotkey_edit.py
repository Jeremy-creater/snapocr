"""Hotkey recorder field for the settings window (PRD F11-2, M3 plan D6).

Click it and press a combination: modifiers plus one main key become a
``Hotkey``. The native key code of the event is used when there is one (so
Shift+1 records "1", not "!", and keypad keys are rejected); without it
(offscreen) the Qt key is mapped. Key events are taken before Qt uses them
for shortcuts, mnemonics or Tab focus moves, so those combinations record too.

On a Mac (M9 WI-8) the native code is the Carbon key code, where 0 is A, so 0
falls back to the Qt key; and Qt swaps the modifiers: the Command key arrives
as ``ControlModifier``, the Control key as ``MetaModifier``.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QFocusEvent, QKeyEvent
from PySide6.QtWidgets import QLineEdit, QWidget

from snapocr.hotkeys import (
    MOD_ALT,
    MOD_CMD,
    MOD_CONTROL,
    MOD_SHIFT,
    MOD_WIN,
    Hotkey,
    check_platform,
    display_hotkey,
    mac_keycode,
    vk_from_mac_keycode,
)

_K = Qt.Key
_M = Qt.KeyboardModifier

# Qt flag -> MOD_* bit and preview text, in display order.
_MODIFIERS = {
    "win32": (
        (_M.ControlModifier, MOD_CONTROL, "Ctrl+"),
        (_M.AltModifier, MOD_ALT, "Alt+"),
        (_M.ShiftModifier, MOD_SHIFT, "Shift+"),
        (_M.MetaModifier, MOD_WIN, "Win+"),  # Qt calls the Windows key Meta
    ),
    "darwin": (
        (_M.MetaModifier, MOD_CONTROL, "⌃"),  # Qt's Meta is the Control key on a Mac
        (_M.AltModifier, MOD_ALT, "⌥"),
        (_M.ShiftModifier, MOD_SHIFT, "⇧"),
        (_M.ControlModifier, MOD_CMD, "⌘"),  # and its Control is the Command key
    ),
}
# QKeyEvent.modifiers() flips the flag of the modifier key the event is about,
# so for these events the flag is set (press) or cleared (release) explicitly.
_MODIFIER_KEYS = {
    _K.Key_Control: _M.ControlModifier,
    _K.Key_Alt: _M.AltModifier,
    _K.Key_Shift: _M.ShiftModifier,
    _K.Key_Meta: _M.MetaModifier,
}

_QT_TO_VK: dict[Qt.Key, int] = {
    **{getattr(_K, f"Key_{c}"): ord(c) for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"},
    **{getattr(_K, f"Key_F{n}"): 0x6F + n for n in range(1, 25)},
    _K.Key_Space: 0x20, _K.Key_Tab: 0x09, _K.Key_Backtab: 0x09, _K.Key_Insert: 0x2D, _K.Key_Delete: 0x2E,
    _K.Key_Home: 0x24, _K.Key_End: 0x23, _K.Key_PageUp: 0x21, _K.Key_PageDown: 0x22,
    _K.Key_Left: 0x25, _K.Key_Up: 0x26, _K.Key_Right: 0x27, _K.Key_Down: 0x28, _K.Key_Print: 0x2C,
}

NO_MODIFIER = {
    "win32": "热键至少要包含 Ctrl、Alt、Shift、Win 中的一个。",
    "darwin": "热键至少要包含 ⌃ Control、⌥ Option、⇧ Shift、⌘ Command 中的一个。",
}
UNSUPPORTED = {
    "win32": "不支持这个键。可以用字母、数字（不是小键盘）、F1–F24、空格、Tab、方向键等。",
    "darwin": "不支持这个键。可以用字母、数字（不是小键盘）、F1–F20、空格、Tab、方向键等。",
}


def _native_vk(event: QKeyEvent, platform: str) -> int | None:
    """The key from the event's native code; 0 means none (offscreen), and on a Mac also A."""
    code = event.nativeVirtualKey()
    if platform == "darwin":
        if code == 0:
            return None
        return vk_from_mac_keycode(code) or 0  # 0: a key no hotkey can use, such as a keypad key
    return code or None


def _vk(event: QKeyEvent, platform: str) -> int | None:
    """A virtual-key code ``Hotkey`` accepts on ``platform``, or None."""
    vk = _native_vk(event, platform)
    if vk is None:
        if event.modifiers() & _M.KeypadModifier:
            return None
        vk = _QT_TO_VK.get(Qt.Key(event.key()))
        if vk is None:
            return None
    try:
        Hotkey(MOD_CONTROL, vk)
    except ValueError:
        return None
    if platform == "darwin" and mac_keycode(vk) is None:  # Insert, PrintScreen, F21-F24
        return None
    return vk


class HotkeyEdit(QLineEdit):
    hotkey_changed = Signal(object)  # Hotkey
    rejected = Signal(str)  # why the pressed combination cannot be used

    def __init__(self, parent: QWidget | None = None, *, platform: str = "win32") -> None:
        super().__init__(parent)
        self._platform = check_platform(platform)
        self._modifiers = _MODIFIERS[platform]
        self.setReadOnly(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setPlaceholderText("点击后按下组合键")
        self._hotkey: Hotkey | None = None

    def hotkey(self) -> Hotkey | None:
        return self._hotkey

    def set_hotkey(self, hotkey: Hotkey | None) -> None:
        self._hotkey = hotkey
        self._show_value()

    def _show_value(self) -> None:
        self.setText("" if self._hotkey is None else display_hotkey(self._hotkey, platform=self._platform))

    def _mods(self, modifiers: Qt.KeyboardModifier) -> int:
        return sum(bit for flag, bit, _ in self._modifiers if modifiers & flag)

    def _show_preview(self, modifiers: Qt.KeyboardModifier) -> None:
        names = [name for flag, _, name in self._modifiers if modifiers & flag]
        if names:
            self.setText("".join(names) + "…")
        else:
            self._show_value()

    def event(self, event: QEvent) -> bool:
        kind = event.type()
        if kind == QEvent.Type.ShortcutOverride:
            event.accept()
            return True
        if kind == QEvent.Type.KeyPress:
            self._on_press(event)
            return True
        if kind == QEvent.Type.KeyRelease:
            key = Qt.Key(event.key())
            if key in _MODIFIER_KEYS and self.text().endswith("…"):
                self._show_preview(event.modifiers() & ~_MODIFIER_KEYS[key])
            return True
        return super().event(event)

    def _on_press(self, event: QKeyEvent) -> None:
        key = Qt.Key(event.key())
        if key in _MODIFIER_KEYS:
            self._show_preview(event.modifiers() | _MODIFIER_KEYS[key])
            return
        mods = self._mods(event.modifiers())
        if key == _K.Key_Escape and not mods:
            self._show_value()
            self.clearFocus()
            return
        vk = _vk(event, self._platform)
        if vk is None or not mods:
            self._show_value()
            self.rejected.emit(UNSUPPORTED[self._platform] if vk is None else NO_MODIFIER[self._platform])
            return
        self._hotkey = Hotkey(mods, vk)
        self._show_value()
        self.hotkey_changed.emit(self._hotkey)

    def focusOutEvent(self, event: QFocusEvent) -> None:
        self._show_value()
        super().focusOutEvent(event)
