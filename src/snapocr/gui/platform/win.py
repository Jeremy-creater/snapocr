"""The Windows kit: the desktop pieces ``launch.py`` takes by name (M9 plan D12). Forwarding only."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication, QWidget

from snapocr.autostart import autostart_command
from snapocr.config.files import instance_name
from snapocr.gui.platform import native_clipboard, shell, single_instance
from snapocr.gui.platform.autostart import RegistryAutostart
from snapocr.gui.platform.capture import DesktopCapture as Capture
from snapocr.gui.platform.glass import NativeGlass
from snapocr.gui.platform.hotkeys import NativeHotkeys as Hotkeys

PLATFORM = "win32"
open_file = shell.open_file
flush_clipboard = native_clipboard.flush

__all__ = ["PLATFORM", "Capture", "Hotkeys", "acquire", "flush_clipboard", "glass", "make_autostart",
           "open_file", "prepare_app", "prepare_overlay"]


def acquire(config: Path) -> single_instance.InstanceLock | None:
    return single_instance.acquire(instance_name(config))


def make_autostart(executable: Path, config: Path, frozen: bool) -> RegistryAutostart:
    return RegistryAutostart(autostart_command(executable, config, frozen))  # F22-2


def glass() -> NativeGlass:
    return NativeGlass()


def prepare_app(app: QApplication) -> None:
    """Nothing to do on Windows."""


def prepare_overlay(widget: QWidget) -> None:
    """Nothing to do on Windows: Qt's stay-on-top already covers the taskbar."""
