"""Tray menu (F5-1): the hotkey actions with their hotkeys, then settings and quit (F11-1, F13-1)."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from PySide6.QtWidgets import QMenu, QSystemTrayIcon, QWidget

from snapocr.actions.outcomes import Notice

from snapocr.actions.messages import COMMAND_LABELS
from snapocr.commands import Command
from snapocr.config.schema import HOTKEY_COMMANDS
from snapocr.hotkeys import Hotkey, format_hotkey


def _text(command: Command, bindings: Mapping[Command, Hotkey]) -> str:
    text = COMMAND_LABELS[command]
    if command in bindings:
        text = f"{text}\t{format_hotkey(bindings[command])}"
    return text


def build_tray_menu(
    bindings: Mapping[Command, Hotkey], on_command: Callable[[Command], None], parent: QWidget | None = None
) -> QMenu:
    menu = QMenu(parent)
    for command in HOTKEY_COMMANDS:
        menu.addAction(_text(command, bindings)).triggered.connect(lambda _=False, c=command: on_command(c))
    menu.addSeparator()
    for command in (Command.SETTINGS, Command.QUIT):
        menu.addAction(COMMAND_LABELS[command]).triggered.connect(lambda _=False, c=command: on_command(c))
    return menu


def update_tray_menu(menu: QMenu, bindings: Mapping[Command, Hotkey]) -> None:
    """Show new hotkeys on the menu built by ``build_tray_menu`` (F11-3)."""
    for action, command in zip(menu.actions(), HOTKEY_COMMANDS, strict=False):
        action.setText(_text(command, bindings))


def notice_icon(notice: Notice) -> QSystemTrayIcon.MessageIcon:
    """F18-3: failures with the warning icon, everything else with the information icon."""
    if notice.warning:
        return QSystemTrayIcon.MessageIcon.Warning
    return QSystemTrayIcon.MessageIcon.Information
