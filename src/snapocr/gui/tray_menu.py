"""Tray menu (F5-1): the hotkey actions with their hotkeys, then settings and quit (F11-1, F13-1)."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from PySide6.QtWidgets import QMenu, QSystemTrayIcon, QWidget

from snapocr.actions.outcomes import Notice

from snapocr.actions.messages import COMMAND_LABELS
from snapocr.commands import Command
from snapocr.config.schema import HOTKEY_COMMANDS
from snapocr.hotkeys import Hotkey, display_hotkey


def _text(command: Command, bindings: Mapping[Command, Hotkey], platform: str) -> str:
    """On a Mac the native menu reads the text after the tab as the shortcut column (M9 WI-7)."""
    text = COMMAND_LABELS[command]
    if command in bindings:
        text = f"{text}\t{display_hotkey(bindings[command], platform=platform)}"
    return text


def build_tray_menu(
    bindings: Mapping[Command, Hotkey], on_command: Callable[[Command], None], parent: QWidget | None = None,
    *, platform: str = "win32",
) -> QMenu:
    menu = QMenu(parent)
    for command in HOTKEY_COMMANDS:
        menu.addAction(_text(command, bindings, platform)).triggered.connect(lambda _=False, c=command: on_command(c))
    menu.addSeparator()
    for command in (Command.SETTINGS, Command.QUIT):
        menu.addAction(COMMAND_LABELS[command]).triggered.connect(lambda _=False, c=command: on_command(c))
    return menu


def update_tray_menu(menu: QMenu, bindings: Mapping[Command, Hotkey], *, platform: str = "win32") -> None:
    """Show new hotkeys on the menu built by ``build_tray_menu`` (F11-3)."""
    for action, command in zip(menu.actions(), HOTKEY_COMMANDS, strict=False):
        action.setText(_text(command, bindings, platform))


def notice_icon(notice: Notice) -> QSystemTrayIcon.MessageIcon:
    """F18-3: failures with the warning icon, everything else with the information icon."""
    if notice.warning:
        return QSystemTrayIcon.MessageIcon.Warning
    return QSystemTrayIcon.MessageIcon.Information
