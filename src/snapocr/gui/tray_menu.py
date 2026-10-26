"""Tray menu (F5-1): the four actions with their hotkeys, then config and quit."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from PySide6.QtWidgets import QMenu, QWidget

from snapocr.actions.messages import COMMAND_LABELS
from snapocr.commands import Command
from snapocr.config.schema import HOTKEY_COMMANDS
from snapocr.hotkeys import Hotkey, format_hotkey


def build_tray_menu(
    bindings: Mapping[Command, Hotkey], on_command: Callable[[Command], None], parent: QWidget | None = None
) -> QMenu:
    menu = QMenu(parent)
    for command in HOTKEY_COMMANDS:
        text = COMMAND_LABELS[command]
        if command in bindings:
            text = f"{text}\t{format_hotkey(bindings[command])}"
        menu.addAction(text).triggered.connect(lambda _=False, c=command: on_command(c))
    menu.addSeparator()
    for command in (Command.OPEN_CONFIG, Command.QUIT):
        menu.addAction(COMMAND_LABELS[command]).triggered.connect(lambda _=False, c=command: on_command(c))
    return menu
