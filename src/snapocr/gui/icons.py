"""The application icon (F5-6), shipped as package data and built by ``tools/make_icon.py``."""

from __future__ import annotations

from importlib.resources import files

from PySide6.QtGui import QIcon


def app_icon() -> QIcon:
    """The multi-size icon (16/24/32/48/256) for the tray, windows and popup."""
    return QIcon(str(files("snapocr.gui") / "assets" / "snapocr.ico"))
