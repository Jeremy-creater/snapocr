"""The macOS screen-recording permission (PRD F23-3, M9 plan D15).

``MacCapture`` checks before every capture; without the permission it asks
once (the first time macOS shows its own prompt) and raises
``CapturePermissionError``, so a wallpaper-only image is never used.
"""

from __future__ import annotations

from snapocr.gui.platform.mac import _cocoa as c


def screen_capture_allowed() -> bool:
    return bool(c.cg.CGPreflightScreenCaptureAccess())


def request_screen_capture() -> bool:
    """Ask macOS for the permission; True at once (and no prompt) when it is already given."""
    return bool(c.cg.CGRequestScreenCaptureAccess())
