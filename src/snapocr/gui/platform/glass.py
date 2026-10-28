"""Acrylic behind the translation window (PRD F20-4; M7 plan D4, D6). Facts and Win32 calls only.

Qt's translucent frameless windows are layered windows, where the documented
``DWMWA_SYSTEMBACKDROP_TYPE`` only paints a grey fallback (measured
2026-10-28); the undocumented ``SetWindowCompositionAttribute`` accent policy
gives real acrylic. Rounded corners and the system shadow come from
``DWMWA_WINDOW_CORNER_PREFERENCE``. Whether acrylic should be used is decided
in ``snapocr.theme``, not here.
"""

from __future__ import annotations

import ctypes
import sys
import winreg

from PySide6.QtWidgets import QWidget

from snapocr.gui.platform import _win32
from snapocr.theme import Color, GlassFacts, abgr

PERSONALIZE_KEY = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"


def _transparency(key_path: str) -> bool:
    """Missing key or value: on, as on a fresh Windows install."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            return winreg.QueryValueEx(key, "EnableTransparency")[0] != 0
    except FileNotFoundError:
        return True


def _battery_saver() -> bool:
    status = _win32.SYSTEM_POWER_STATUS()
    _win32.kernel32.GetSystemPowerStatus(ctypes.byref(status))
    return status.SystemStatusFlag == 1


def read_facts(*, key_path: str = PERSONALIZE_KEY) -> GlassFacts:
    return GlassFacts(sys.getwindowsversion().build, _transparency(key_path), _battery_saver())


def _accent_data(policy: _win32.ACCENT_POLICY) -> _win32.WINDOWCOMPOSITIONATTRIBDATA:
    return _win32.WINDOWCOMPOSITIONATTRIBDATA(
        _win32.WCA_ACCENT_POLICY, ctypes.cast(ctypes.byref(policy), ctypes.c_void_p), ctypes.sizeof(policy)
    )


def set_acrylic(hwnd: int, tint: int | None) -> bool:
    """Acrylic with the 0xAABBGGRR ``tint``, or none; round corners either way. True if Windows took it.

    Windows cannot read the accent back (``GetWindowCompositionAttribute`` fails),
    so the gui lane checks the result on screen."""
    if tint is None:
        policy = _win32.ACCENT_POLICY(_win32.ACCENT_DISABLED, 0, 0, 0)
    else:
        policy = _win32.ACCENT_POLICY(_win32.ACCENT_ENABLE_ACRYLICBLURBEHIND, _win32.ACCENT_FLAG_GRADIENT_COLOR, tint, 0)
    ok = bool(_win32.user32.SetWindowCompositionAttribute(hwnd, ctypes.byref(_accent_data(policy))))
    corner = ctypes.c_int(_win32.DWMWCP_ROUND)
    _win32.dwmapi.DwmSetWindowAttribute(hwnd, _win32.DWMWA_WINDOW_CORNER_PREFERENCE, ctypes.byref(corner), 4)
    return ok


class NativeGlass:
    """The controller's ``Glass`` boundary on the real desktop."""

    def facts(self) -> GlassFacts:
        return read_facts()

    def apply(self, widget: QWidget, tint: Color | None) -> bool:
        return set_acrylic(int(widget.winId()), None if tint is None else abgr(tint))
