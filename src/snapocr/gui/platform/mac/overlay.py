"""Overlays above the menu bar and the Dock, taking the keys (PRD F23-4, M9 plan D16).

Called once per overlay right after Qt has shown it, so the NSWindow exists
and Qt has already applied its own level (8 for stay-on-top), which this raises.
"""

from __future__ import annotations

import ctypes

from PySide6.QtWidgets import QWidget

from snapocr.gui.platform.mac import _cocoa as c

_BEHAVIOR = c.NSWindowCollectionBehaviorCanJoinAllSpaces | c.NSWindowCollectionBehaviorFullScreenAuxiliary


def prepare_overlay(widget: QWidget) -> None:
    window = c.send(ctypes.c_void_p(int(widget.winId())), "window")  # winId is the NSView
    c.send(window, "setLevel:", c.NSStatusWindowLevel, argtypes=(ctypes.c_long,), restype=None)
    c.send(window, "setCollectionBehavior:", _BEHAVIOR, argtypes=(ctypes.c_ulong,), restype=None)
    # Qt.Tool makes an NSPanel, which hides whenever another app is active.
    c.send(window, "setHidesOnDeactivate:", False, argtypes=(ctypes.c_bool,), restype=None)
    c.send(c.ns_app(), "activateIgnoringOtherApps:", True, argtypes=(ctypes.c_bool,), restype=None)
