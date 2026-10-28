"""System-tray icon with the menu and notices (F5-1, F7); the real ``Notifier``."""

from __future__ import annotations

from PySide6.QtCore import QObject
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from snapocr.actions.outcomes import Notice
from snapocr.gui.tray_menu import notice_icon

NOTICE_MS = 5000


class Tray(QObject):
    def __init__(self, menu: QMenu, icon: QIcon, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._icon = QSystemTrayIcon(icon, self)
        self._icon.setContextMenu(menu)
        self._icon.setToolTip("snapocr")

    @property
    def icon(self) -> QSystemTrayIcon:
        return self._icon

    def show(self) -> None:
        self._icon.show()

    def hide(self) -> None:
        self._icon.hide()

    def notify(self, notice: Notice) -> None:
        self._icon.showMessage(notice.title, notice.body, notice_icon(notice), NOTICE_MS)
