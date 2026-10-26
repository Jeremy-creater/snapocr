"""Keep the clipboard after snapocr exits (F7-1, R7).

Qt puts data on the Windows clipboard as a delayed-rendering OLE object and
renders it for good (``OleFlushClipboard``) only when the QGuiApplication is
destroyed. Python's interpreter shutdown does not reliably get there, so a
screenshot could vanish when snapocr quits (WI-21 measured about one exit in
two). ``flush()`` renders it explicitly; call it on the GUI thread before
leaving the event loop.
"""

from __future__ import annotations

import ctypes

_ole32 = ctypes.WinDLL("ole32")
_ole32.OleFlushClipboard.argtypes = []
_ole32.OleFlushClipboard.restype = ctypes.c_long  # HRESULT


def flush() -> int:
    """Render the data snapocr put on the clipboard; returns the HRESULT (0 = S_OK)."""
    return _ole32.OleFlushClipboard()
