"""The Mac kit: the desktop pieces ``launch.py`` takes by name (PRD F23, M9 plan D12, D17, D20)."""

from __future__ import annotations

import ctypes
import subprocess
import tempfile
from pathlib import Path

from PySide6.QtWidgets import QApplication

from snapocr.config.files import lock_path
from snapocr.gui.boundaries import NoGlass
from snapocr.gui.platform.mac import _cocoa as c
from snapocr.gui.platform.mac import single_instance
from snapocr.gui.platform.mac.capture import MacCapture as Capture
from snapocr.gui.platform.mac.hotkeys import CarbonHotkeys as Hotkeys
from snapocr.gui.platform.mac.overlay import prepare_overlay

PLATFORM = "darwin"

__all__ = ["PLATFORM", "Capture", "Hotkeys", "acquire", "flush_clipboard", "glass", "make_autostart",
           "open_file", "prepare_app", "prepare_overlay"]


def acquire(config: Path, lock_dir: Path | None = None) -> single_instance.InstanceLock | None:
    """F23-8: one instance per config file; the lock file lives in ``$TMPDIR``."""
    return single_instance.acquire(lock_path(config, Path(lock_dir or tempfile.gettempdir())))


class NoAutostart:
    """Start at login is not there yet on the Mac (LaunchAgent: M9 WI-12, WI-13)."""

    def is_enabled(self) -> bool:
        return False

    def set_enabled(self, enabled: bool) -> None:
        if enabled:
            raise OSError("macOS 版还不支持开机自启动")


def make_autostart(executable: Path, config: Path, frozen: bool) -> NoAutostart:
    return NoAutostart()


def glass() -> NoGlass:
    """F23-9: solid windows on the Mac for now; the settings window says so (F20-4)."""
    return NoGlass(PLATFORM)


def open_file(path: Path) -> None:
    """D20: the default text editor; ``.toml`` often has no app of its own. ``OSError`` when it fails."""
    result = subprocess.run(["open", "-t", str(path)], capture_output=True, text=True)
    if result.returncode != 0:
        raise OSError(result.stderr.strip() or f"open -t 失败（{result.returncode}）")


def flush_clipboard() -> None:
    """The Mac pasteboard keeps what snapocr put there after it exits (checked by WI-21)."""


def prepare_app(app: QApplication) -> None:
    """D17: no Dock icon and no app menu; before the menu bar icon is shown."""
    c.send(c.ns_app(), "setActivationPolicy:", c.NSApplicationActivationPolicyAccessory,
           argtypes=(ctypes.c_long,), restype=ctypes.c_bool)
