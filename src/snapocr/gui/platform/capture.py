"""Capture the whole virtual desktop with GDI (F6-1, F6-2, plan D4).

One ``BitBlt`` (with ``CAPTUREBLT``, so layered windows are included) of the
virtual desktop in physical pixels, read back top-down as 32-bit BGRX, which
is exactly ``QImage.Format_RGB32``. Qt 6 runs Per-Monitor-V2 aware, so GDI
coordinates are physical pixels.
"""

from __future__ import annotations

import ctypes
from collections.abc import Callable

from PySide6.QtGui import QImage

from snapocr.geometry import Rect, ScreenInfo, ScreenMismatch
from snapocr.gui.boundaries import Capture, CaptureError
from snapocr.gui.platform import _win32
from snapocr.gui.platform.screens import qt_screen_infos

ScreensFn = Callable[[], tuple[tuple[ScreenInfo, ...], dict[str, Rect]]]


def virtual_desktop() -> Rect:
    m = _win32.user32.GetSystemMetrics
    return Rect(m(_win32.SM_XVIRTUALSCREEN), m(_win32.SM_YVIRTUALSCREEN),
                m(_win32.SM_CXVIRTUALSCREEN), m(_win32.SM_CYVIRTUALSCREEN))


def _blit(rect: Rect) -> QImage | None:
    """BitBlt straight into a top-down 32-bit DIB section, then one copy into Qt-owned memory.

    Skips the zero-filled buffer, ``GetDIBits`` and the ``bytes`` copy of the
    first version: about 45 ms less on a 7280x2160 desktop (M3 WI-8).
    """
    w, h = rect.w, rect.h
    screen_dc = _win32.user32.GetDC(None)
    mem_dc = _win32.gdi32.CreateCompatibleDC(screen_dc)
    header = _win32.BITMAPINFOHEADER(ctypes.sizeof(_win32.BITMAPINFOHEADER), w, -h, 1, 32, _win32.BI_RGB)
    bits = ctypes.c_void_p()
    bitmap = _win32.gdi32.CreateDIBSection(mem_dc, ctypes.byref(header), _win32.DIB_RGB_COLORS, ctypes.byref(bits), None, 0)
    try:
        old = _win32.gdi32.SelectObject(mem_dc, bitmap)  # a failed DIB section makes BitBlt fail too
        copied = _win32.gdi32.BitBlt(mem_dc, 0, 0, w, h, screen_dc, rect.x, rect.y, _win32.SRCCOPY | _win32.CAPTUREBLT)
        _win32.gdi32.SelectObject(mem_dc, old)
        _win32.gdi32.GdiFlush()  # the DIB memory is complete only after GDI's batch is flushed
        ok = bool(bitmap and bits.value and copied)
        pixels = (ctypes.c_ubyte * (w * h * 4)).from_address(bits.value) if ok else None
        return QImage(pixels, w, h, w * 4, QImage.Format.Format_RGB32).copy() if ok else None  # detach before the DIB is freed
    finally:
        _win32.gdi32.DeleteObject(bitmap)
        _win32.gdi32.DeleteDC(mem_dc)
        _win32.user32.ReleaseDC(None, screen_dc)


def grab_physical(rect: Rect) -> QImage:
    """The physical pixels of ``rect`` (virtual-desktop coordinates) as an RGB32 image."""
    image = _blit(rect) if rect.w > 0 and rect.h > 0 else None
    if image is None:
        raise CaptureError(f"屏幕截取失败（GDI，区域 {rect.x},{rect.y} {rect.w}x{rect.h}）")
    return image


class DesktopCapture:
    """The real ``CaptureProvider``: screens first, then one grab of the virtual desktop."""

    def __init__(self, screens: ScreensFn = qt_screen_infos) -> None:
        self._screens = screens

    def capture(self) -> Capture:
        try:
            screens, work = self._screens()
        except ScreenMismatch as err:
            raise CaptureError(f"Qt 和 Windows 的屏幕信息对不上：{err}") from err
        v = virtual_desktop()
        return Capture(grab_physical(v), (v.x, v.y), screens, work)
