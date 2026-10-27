"""Write action results to the system clipboard (F7-1, F7-2, F16-2; plan D6).

A screenshot goes in as one QMimeData: the image itself (Qt turns it into
CF_DIB / CF_DIBV5 on Windows) and the PNG bytes, both as "image/png" (for Qt
programs) and as the registered Windows format "PNG", which Office and
browsers prefer.
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QMimeData
from PySide6.QtGui import QGuiApplication

from snapocr.actions.outcomes import ClipboardAction, ClipboardPng, ClipboardTable, ClipboardText, NoClipboardChange
from snapocr.gui.imageops import decode_png

WINDOWS_PNG = 'application/x-qt-windows-mime;value="PNG"'


def set_text(text: str) -> None:
    QGuiApplication.clipboard().setText(text)


def set_png(png: bytes) -> None:
    """Raises ``ValueError`` (clipboard untouched) when ``png`` is not a PNG."""
    image = decode_png(png)
    mime = QMimeData()
    mime.setImageData(image)
    mime.setData("image/png", QByteArray(png))
    # Qt registers "image/png" under that literal name; Office and browsers read
    # the registered format "PNG", which only this Windows-mime name produces (WI-21).
    mime.setData(WINDOWS_PNG, QByteArray(png))
    QGuiApplication.clipboard().setMimeData(mime)  # the clipboard takes ownership


def set_table(markdown: str, html: str) -> None:
    """F16-2: one QMimeData with the HTML (Qt offers it as CF_HTML on Windows) and the Markdown as text."""
    mime = QMimeData()
    mime.setHtml(html)
    mime.setText(markdown)
    QGuiApplication.clipboard().setMimeData(mime)


def apply(action: ClipboardAction) -> bool:
    """Carry out an action's clipboard result; True when the clipboard changed."""
    if isinstance(action, ClipboardText):
        set_text(action.text)
        return True
    if isinstance(action, ClipboardPng):
        set_png(action.png)
        return True
    if isinstance(action, ClipboardTable):
        set_table(action.markdown, action.html)
        return True
    if isinstance(action, NoClipboardChange):
        return False
    raise TypeError(f"expected a clipboard action, got {type(action).__name__}")
