"""Write action results to the system clipboard (F7-1, F7-2; plan D6).

A screenshot goes in as one QMimeData with two formats: the image itself (Qt
turns it into CF_DIB / CF_DIBV5 on Windows) and the PNG bytes under
"image/png" (registered format "PNG"), which Office and browsers prefer.
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QMimeData
from PySide6.QtGui import QGuiApplication

from snapocr.actions.outcomes import ClipboardAction, ClipboardPng, ClipboardText, NoClipboardChange
from snapocr.gui.imageops import decode_png


def set_text(text: str) -> None:
    QGuiApplication.clipboard().setText(text)


def set_png(png: bytes) -> None:
    """Raises ``ValueError`` (clipboard untouched) when ``png`` is not a PNG."""
    image = decode_png(png)
    mime = QMimeData()
    mime.setImageData(image)
    mime.setData("image/png", QByteArray(png))
    QGuiApplication.clipboard().setMimeData(mime)  # the clipboard takes ownership


def apply(action: ClipboardAction) -> bool:
    """Carry out an action's clipboard result; True when the clipboard changed."""
    if isinstance(action, ClipboardText):
        set_text(action.text)
        return True
    if isinstance(action, ClipboardPng):
        set_png(action.png)
        return True
    if isinstance(action, NoClipboardChange):
        return False
    raise TypeError(f"expected a clipboard action, got {type(action).__name__}")
