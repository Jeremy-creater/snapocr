"""M5 WI-3: the tray shows a warning notice with the warning icon (PRD F18-3; M5 plan D5)."""

from PySide6.QtWidgets import QSystemTrayIcon

from snapocr.actions.outcomes import Notice
from snapocr.gui.tray_menu import notice_icon


def test_the_tray_icon_follows_the_notice():
    assert notice_icon(Notice("保存失败", "x", warning=True)) is QSystemTrayIcon.MessageIcon.Warning
    assert notice_icon(Notice("已复制截图", "")) is QSystemTrayIcon.MessageIcon.Information
