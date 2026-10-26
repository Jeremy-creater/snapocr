"""M2 WI-17: tray menu (PRD F5-1).

Pinned here:
- Order: 截图, OCR, 翻译, 上次结果, separator, 打开配置文件, 退出.
- A command with a hotkey binding shows it after a tab ("OCR\\tAlt+2");
  an unbound one shows only its label.
- Triggering an action calls ``on_command`` with its command.
"""

import pytest

from snapocr.commands import Command
from snapocr.config.schema import DEFAULT_HOTKEYS
from snapocr.gui.tray_menu import build_tray_menu
from snapocr.hotkeys import parse_hotkey

pytestmark = pytest.mark.usefixtures("qapp")


def texts(menu):
    return ["---" if a.isSeparator() else a.text() for a in menu.actions()]


def test_default_menu_texts_and_order():
    menu = build_tray_menu(DEFAULT_HOTKEYS, lambda c: None)
    assert texts(menu) == ["截图\tAlt+1", "OCR\tAlt+2", "翻译\tAlt+3", "上次结果\tAlt+4", "---", "打开配置文件", "退出"]


def test_custom_and_missing_bindings():
    bindings = {Command.CAPTURE: parse_hotkey("Ctrl+Shift+F1"), Command.TRANSLATE: parse_hotkey("Win+T")}
    menu = build_tray_menu(bindings, lambda c: None)
    assert texts(menu) == ["截图\tCtrl+Shift+F1", "OCR", "翻译\tWin+T", "上次结果", "---", "打开配置文件", "退出"]


def test_triggering_actions_reports_commands():
    seen = []
    menu = build_tray_menu(DEFAULT_HOTKEYS, seen.append)
    for action in menu.actions():
        if not action.isSeparator():
            action.trigger()
    assert seen == [Command.CAPTURE, Command.OCR, Command.TRANSLATE, Command.LAST_RESULT, Command.OPEN_CONFIG, Command.QUIT]
