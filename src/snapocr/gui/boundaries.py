"""What the controller needs from the desktop; ``snapocr.gui.platform`` provides the real ones.

Tests use fakes with the same shape (``tests/support/fake_desktop.py``).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol

from PySide6.QtGui import QImage

from snapocr.actions.outcomes import Notice
from snapocr.geometry import Point, Rect, ScreenInfo


class CaptureError(Exception):
    """The screen could not be captured; the message is shown to the user."""


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
