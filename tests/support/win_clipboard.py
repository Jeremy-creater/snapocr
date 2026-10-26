"""Read the native Windows clipboard for gui-lane checks (M2 WI-21), and save / restore it.

Reads happen through raw user32 calls so the test sees what other programs
(Paint, Word, WeChat) see, not what Qt hands back to itself.
"""

from __future__ import annotations

import ctypes
import struct
import time
from ctypes import wintypes

from PySide6.QtCore import QMimeData
from PySide6.QtGui import QColor, QGuiApplication, QImage

_u = ctypes.WinDLL("user32", use_last_error=True)
_k = ctypes.WinDLL("kernel32", use_last_error=True)
_u.OpenClipboard.argtypes = [wintypes.HWND]
_u.OpenClipboard.restype = wintypes.BOOL
_u.CloseClipboard.restype = wintypes.BOOL
_u.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
_u.IsClipboardFormatAvailable.restype = wintypes.BOOL
_u.GetClipboardData.argtypes = [wintypes.UINT]
_u.GetClipboardData.restype = wintypes.HANDLE
_u.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
_u.RegisterClipboardFormatW.restype = wintypes.UINT
_k.GlobalLock.argtypes = [wintypes.HGLOBAL]
_k.GlobalLock.restype = ctypes.c_void_p
_k.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
_k.GlobalSize.argtypes = [wintypes.HGLOBAL]
_k.GlobalSize.restype = ctypes.c_size_t

CF_UNICODETEXT = 13
CF_DIB = 8
PNG = _u.RegisterClipboardFormatW("PNG")


def _open() -> None:
    for _ in range(50):  # another program may hold the clipboard for a moment
        if _u.OpenClipboard(None):
            return
        time.sleep(0.02)
    raise OSError(f"OpenClipboard failed (error {ctypes.get_last_error()})")


def read(fmt: int) -> bytes | None:
    """The raw bytes of ``fmt``, or None when that format is not on the clipboard."""
    _open()
    try:
        if not _u.IsClipboardFormatAvailable(fmt):
            return None
        handle = _u.GetClipboardData(fmt)
        if not handle:
            return None
        ptr = _k.GlobalLock(handle)
        try:
            return ctypes.string_at(ptr, _k.GlobalSize(handle))
        finally:
            _k.GlobalUnlock(handle)
    finally:
        _u.CloseClipboard()


def read_text() -> str | None:
    data = read(CF_UNICODETEXT)
    return None if data is None else data.decode("utf-16-le").split("\x00", 1)[0]


def decode_dib(data: bytes) -> QImage:
    """A CF_DIB (BITMAPINFOHEADER + pixels; 24 or 32 bpp, BI_RGB or BI_BITFIELDS) as RGB32."""
    size, w, h, _planes, bpp, compression = struct.unpack_from("<IiiHHI", data, 0)
    offset = size + (12 if compression == 3 and size == 40 else 0)
    stride = (w * bpp // 8 + 3) & ~3
    bottom_up = h > 0
    h = abs(h)
    image = QImage(w, h, QImage.Format.Format_RGB32)
    step = bpp // 8
    for row in range(h):
        src_row = (h - 1 - row) if bottom_up else row
        base = offset + src_row * stride
        for x in range(w):
            b, g, r = data[base + x * step : base + x * step + 3]
            image.setPixelColor(x, row, QColor(r, g, b))
    return image


def snapshot() -> QMimeData:
    """A copy of everything Qt can read from the clipboard now."""
    current = QGuiApplication.clipboard().mimeData()
    copy = QMimeData()
    for fmt in current.formats():
        copy.setData(fmt, current.data(fmt))
    return copy


def restore(saved: QMimeData) -> None:
    QGuiApplication.clipboard().setMimeData(saved)
    # Render it now, or it may vanish when the test process exits (R7, WI-21).
    from snapocr.gui.platform.native_clipboard import flush

    flush()
