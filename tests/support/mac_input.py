"""Synthetic key presses on the real Mac desktop for the gui-mac lane (M9 plan D22).

``CGEventPost`` needs the Accessibility permission for the app that runs the
tests (the terminal). Without it ``require_accessibility`` FAILS, never skips,
and says where to turn it on.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import time

import pytest

from snapocr.hotkeys import MOD_ALT, MOD_CMD, MOD_CONTROL, MOD_SHIFT, mac_keycode

_cg = ctypes.CDLL(ctypes.util.find_library("CoreGraphics"))
_ax = ctypes.CDLL(ctypes.util.find_library("ApplicationServices"))
_cf = ctypes.CDLL(ctypes.util.find_library("CoreFoundation"))

_cg.CGEventCreateKeyboardEvent.restype = ctypes.c_void_p
_cg.CGEventCreateKeyboardEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint16, ctypes.c_bool]
_cg.CGEventSetFlags.restype = None
_cg.CGEventSetFlags.argtypes = [ctypes.c_void_p, ctypes.c_uint64]
_cg.CGEventPost.restype = None
_cg.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
_ax.AXIsProcessTrusted.restype = ctypes.c_bool
_ax.AXIsProcessTrusted.argtypes = []
_cf.CFRelease.argtypes = [ctypes.c_void_p]

kCGHIDEventTap = 0
# CGEventFlags
_FLAGS = {MOD_SHIFT: 0x00020000, MOD_CONTROL: 0x00040000, MOD_ALT: 0x00080000, MOD_CMD: 0x00100000}
# A real keyboard sets SecondaryFn on F-keys and the navigation keys; without it
# Carbon does not match a hotkey on F19 (measured 2026-10-30, M9 WI-14).
kCGEventFlagMaskSecondaryFn = 0x00800000
_FN_VKS = frozenset(range(0x70, 0x88)) | frozenset(range(0x21, 0x29)) | {0x2D, 0x2E}

ACCESSIBILITY_HELP = (
    "gui-mac needs the Accessibility permission for the terminal that runs the tests: "
    "System Settings > Privacy & Security > Accessibility, turn on your terminal app, then rerun."
)


def require_accessibility() -> None:
    if not _ax.AXIsProcessTrusted():
        pytest.fail(ACCESSIBILITY_HELP, pytrace=False)


def press_combo(mods: int, vk: int) -> None:
    """Press and release ``vk`` with the MOD_* modifiers held, as the HID system would."""
    require_accessibility()
    code = mac_keycode(vk)
    assert code is not None, f"no Mac key for VK {vk:#x}"
    flags = sum(bit for mod, bit in _FLAGS.items() if mods & mod)
    if vk in _FN_VKS:
        flags |= kCGEventFlagMaskSecondaryFn
    for down in (True, False):
        event = _cg.CGEventCreateKeyboardEvent(None, code, down)
        _cg.CGEventSetFlags(event, flags)
        _cg.CGEventPost(kCGHIDEventTap, event)
        _cf.CFRelease(event)
        time.sleep(0.02)
