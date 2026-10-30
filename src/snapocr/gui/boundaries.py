"""What the controller needs from the desktop; ``snapocr.gui.platform`` provides the real ones.

Tests use fakes with the same shape (``tests/support/fake_desktop.py``).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QWidget

from snapocr.actions.outcomes import Notice
from snapocr.geometry import Point, Rect, ScreenInfo
from snapocr.theme import Color, GlassFacts


class CaptureError(Exception):
    """The screen could not be captured; the message is shown to the user."""


class CapturePermissionError(CaptureError):
    """macOS has not given the screen-recording permission (F23-3); nothing was captured."""


@dataclass(frozen=True)
class Capture:
    """The whole virtual desktop in physical pixels, taken when a capture command fires."""

    image: QImage
    origin: Point  # virtual-desktop top-left; may be negative
    screens: tuple[ScreenInfo, ...]
    work_areas: Mapping[str, Rect] = field(default_factory=dict)  # logical, by screen name


class CaptureProvider(Protocol):
    def capture(self) -> Capture: ...


class Notifier(Protocol):
    def notify(self, notice: Notice) -> None: ...


class HotkeyBackend(Protocol):
    """Win32 semantics: 0 on success, otherwise the error code."""

    def register(self, hotkey_id: int, mods: int, vk: int) -> int: ...

    def unregister(self, hotkey_id: int) -> int: ...


class Glass(Protocol):
    """Acrylic behind a window (F20-4); ``apply`` returns whether Windows took it."""

    def facts(self) -> GlassFacts: ...

    def apply(self, widget: QWidget, tint: Color | None) -> bool: ...


class NoGlass:
    """No acrylic anywhere: reports a pre-Windows 11 build, or a Mac, so every look is solid."""

    def __init__(self, platform: str = "win32") -> None:
        self._platform = platform

    def facts(self) -> GlassFacts:
        return GlassFacts(build=0, transparency=False, battery_saver=False, platform=self._platform)

    def apply(self, widget: QWidget, tint: Color | None) -> bool:
        return tint is None


class Autostart(Protocol):
    """Start at login (F11-6); both methods raise ``OSError`` when the system refuses."""

    def is_enabled(self) -> bool: ...

    def set_enabled(self, enabled: bool) -> None: ...
