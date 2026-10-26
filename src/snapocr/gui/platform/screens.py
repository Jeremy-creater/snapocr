"""Screens: Win32 monitors paired with Qt screens (F6-2, plan D4).

On Windows, ``QScreen.name()`` is the monitor model, not the device name, but
Qt keeps each screen's origin in native pixels. So the device name is looked
up at that origin, and WI-3 ``match_screens`` then checks that physical size /
dpr agrees with Qt's logical size.
"""

from __future__ import annotations

import ctypes

from PySide6.QtGui import QGuiApplication

from snapocr.geometry import Rect, ScreenInfo, match_screens
from snapocr.gui.platform import _win32


def _monitor_info(hmonitor) -> _win32.MONITORINFOEXW:
    info = _win32.MONITORINFOEXW()
    info.cbSize = ctypes.sizeof(info)
    _win32.user32.GetMonitorInfoW(hmonitor, ctypes.byref(info))
    return info


def enum_monitors() -> list[tuple[str, Rect]]:
    """(device name, physical rect) of every monitor."""
    found: list[tuple[str, Rect]] = []

    def collect(hmonitor, _hdc, _rect, _data):
        info = _monitor_info(hmonitor)
        r = info.rcMonitor
        found.append((info.szDevice, Rect(r.left, r.top, r.right - r.left, r.bottom - r.top)))
        return True

    _win32.user32.EnumDisplayMonitors(None, None, _win32.MONITORENUMPROC(collect), 0)
    return found


def _device_at(x: int, y: int) -> str:
    hmonitor = _win32.user32.MonitorFromPoint(_win32.wintypes.POINT(x, y), _win32.MONITOR_DEFAULTTONEAREST)
    return _monitor_info(hmonitor).szDevice


def is_per_monitor_v2() -> bool:
    """Qt 6 makes the process PMv2-aware; GDI coordinates are then physical pixels."""
    context = _win32.user32.GetThreadDpiAwarenessContext()
    return bool(_win32.user32.AreDpiAwarenessContextsEqual(context, _win32.DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2))


def qt_screen_infos() -> tuple[tuple[ScreenInfo, ...], dict[str, Rect]]:
    """ScreenInfos in Qt's order and each screen's available (work) area in logical coordinates.

    Raises ``ScreenMismatch`` when Qt and Win32 disagree.
    """
    qt_screens, work = [], {}
    for screen in QGuiApplication.screens():
        g, a = screen.geometry(), screen.availableGeometry()
        name = _device_at(g.x(), g.y())
        qt_screens.append((name, Rect(g.x(), g.y(), g.width(), g.height()), screen.devicePixelRatio()))
        work[name] = Rect(a.x(), a.y(), a.width(), a.height())
    return tuple(match_screens(qt_screens, enum_monitors())), work
