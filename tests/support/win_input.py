"""Win32 helpers for the gui lane (M2 WI-19 onwards): key injection and a foreign hotkey owner.

Only gui-lane tests import this; ctypes in tests is fine (the boundary rule is
about ``src``).
"""

from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
_user32.RegisterHotKey.restype = wintypes.BOOL
_user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.UnregisterHotKey.restype = wintypes.BOOL
_user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_user32.PostMessageW.restype = wintypes.BOOL

VK_CONTROL, VK_MENU, VK_SHIFT, VK_LWIN = 0x11, 0x12, 0x10, 0x5B
_MOD_KEYS = ((0x2, VK_CONTROL), (0x1, VK_MENU), (0x4, VK_SHIFT), (0x8, VK_LWIN))
KEYEVENTF_KEYUP = 0x2
WM_HOTKEY = 0x0312


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", _KEYBDINPUT), ("pad", ctypes.c_byte * 32)]

    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


def press_combo(mods: int, vk: int) -> None:
    """Inject the modifiers and key down, then up, with SendInput."""
    keys = [k for bit, k in _MOD_KEYS if mods & bit] + [vk]
    seq = [(k, 0) for k in keys] + [(k, KEYEVENTF_KEYUP) for k in reversed(keys)]
    inputs = (_INPUT * len(seq))()
    for i, (k, flags) in enumerate(seq):
        inputs[i].type = 1  # INPUT_KEYBOARD
        inputs[i].ki = _KEYBDINPUT(k, 0, flags, 0, 0)
    sent = _user32.SendInput(len(seq), inputs, ctypes.sizeof(_INPUT))
    if sent != len(seq):
        raise OSError(f"SendInput sent {sent} of {len(seq)} events (error {ctypes.get_last_error()})")


def register_raw(mods: int, vk: int, hotkey_id: int = 0xBEEF) -> bool:
    """RegisterHotKey on this thread with no window; True on success."""
    return bool(_user32.RegisterHotKey(None, hotkey_id, mods, vk))


def unregister_raw(hotkey_id: int = 0xBEEF) -> bool:
    return bool(_user32.UnregisterHotKey(None, hotkey_id))


def post_hotkey_message(hwnd: int, hotkey_id: int) -> bool:
    return bool(_user32.PostMessageW(hwnd, WM_HOTKEY, hotkey_id, 0))


class ForeignHotkeyOwner:
    """Holds a combination on its own thread, like another program would (F5-3 real path)."""

    def __init__(self, mods: int, vk: int):
        self._mods, self._vk = mods, vk
        self._ready, self._stop = threading.Event(), threading.Event()
        self.ok = False
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        self.ok = register_raw(self._mods, self._vk, 0xCAFE)
        self._ready.set()
        self._stop.wait(30)
        if self.ok:
            unregister_raw(0xCAFE)

    def __enter__(self):
        self._thread.start()
        self._ready.wait(5)
        if not self.ok:
            raise OSError("could not pre-register the hotkey in the helper thread")
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join(5)
