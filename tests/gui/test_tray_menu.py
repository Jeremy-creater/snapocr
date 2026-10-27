"""M2 WI-17: tray menu (PRD F5-1).

Pinned here:
- Order: 截图, OCR, 翻译, 上次结果, separator, 设置…, 退出 (M3: 打开配置文件 moved
  into the settings window, PRD F5-1, F11-5).
- ``update_tray_menu`` rewrites the hotkey texts in place (F11-3).
- A command with a hotkey binding shows it after a tab ("OCR\\tAlt+2");
  an unbound one shows only its label.
- Triggering an action calls ``on_command`` with its command.
"""

import pytest

from snapocr.commands import Command
from snapocr.config.schema import DEFAULT_HOTKEYS
from snapocr.gui.tray_menu import build_tray_menu, update_tray_menu
from snapocr.hotkeys import parse_hotkey

pytestmark = pytest.mark.usefixtures("qapp")


def texts(menu):
    return ["---" if a.isSeparator() else a.text() for a in menu.actions()]


def test_default_menu_texts_and_order():
    menu = build_tray_menu(DEFAULT_HOTKEYS, lambda c: None)
    assert texts(menu) == ["截图\tAlt+1", "OCR\tAlt+2", "翻译\tAlt+3", "上次结果\tAlt+4", "代码 OCR\tAlt+5", "---",
                           "设置…", "退出"]


def test_custom_and_missing_bindings():
    bindings = {Command.CAPTURE: parse_hotkey("Ctrl+Shift+F1"), Command.TRANSLATE: parse_hotkey("Win+T")}
    menu = build_tray_menu(bindings, lambda c: None)
    assert texts(menu) == ["截图\tCtrl+Shift+F1", "OCR", "翻译\tWin+T", "上次结果", "代码 OCR", "---", "设置…", "退出"]


def test_triggering_actions_reports_commands():
    seen = []
    menu = build_tray_menu(DEFAULT_HOTKEYS, seen.append)
    for action in menu.actions():
        if not action.isSeparator():
            action.trigger()
    assert seen == [Command.CAPTURE, Command.OCR, Command.TRANSLATE, Command.LAST_RESULT, Command.CODE_OCR,
                    Command.SETTINGS, Command.QUIT]


def test_update_rewrites_hotkey_texts_in_place():
    seen = []
    menu = build_tray_menu(DEFAULT_HOTKEYS, seen.append)
    actions = menu.actions()
    update_tray_menu(menu, {Command.CAPTURE: parse_hotkey("Ctrl+Q"), Command.LAST_RESULT: parse_hotkey("Alt+4")})
    assert menu.actions() == actions
    assert texts(menu) == ["截图\tCtrl+Q", "OCR", "翻译", "上次结果\tAlt+4", "代码 OCR", "---", "设置…", "退出"]
    actions[1].trigger()
    assert seen == [Command.OCR]
