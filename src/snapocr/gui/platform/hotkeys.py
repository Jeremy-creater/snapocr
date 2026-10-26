"""Global hotkeys on a hidden window; WM_HOTKEY through a native event filter (F5-3, F5-5, plan D3).

Registration and release happen on the GUI thread, against the HWND of a
hidden native widget (window messages survive Win32 modal loops, thread
messages do not). ``register`` / ``unregister`` match the ``HotkeyBackend``
shape that ``snapocr.hotkeys.register_all`` and the controller use.
"""

from __future__ import annotations

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication, QObject, Qt, Signal
from PySide6.QtWidgets import QWidget

from snapocr.gui.platform import _win32


class _HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, hwnd: int, emit) -> None:
        super().__init__()
        self._hwnd = hwnd
        self._emit = emit

    def nativeEventFilter(self, event_type, message):  # noqa: N802 - Qt override
        msg = _win32.MSG.from_address(int(message))
        if msg.message == _win32.WM_HOTKEY and msg.hWnd == self._hwnd:
            self._emit(int(msg.wParam))
            return True, 0
        return False, 0


class NativeHotkeys(QObject):
    activated = Signal(int)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._window = QWidget()
        self._window.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
        self._hwnd = int(self._window.winId())  # creates the native window; never shown
        self._filter = _HotkeyFilter(self._hwnd, self.activated.emit)
        QCoreApplication.instance().installNativeEventFilter(self._filter)
        self._closed = False

    @property
    def hwnd(self) -> int:
        return self._hwnd

    def register(self, hotkey_id: int, mods: int, vk: int) -> int:
        """0 on success, otherwise the Win32 error (1409: taken by another program)."""
        if _win32.user32.RegisterHotKey(self._hwnd, hotkey_id, mods, vk):
            return 0
        return _win32.get_last_error()

    def unregister(self, hotkey_id: int) -> int:
        if _win32.user32.UnregisterHotKey(self._hwnd, hotkey_id):
            return 0
        return _win32.get_last_error()

    def close(self) -> None:
        """Stop listening and destroy the window; release the hotkeys first (``unregister_all``)."""
        if self._closed:
            return
        self._closed = True
        QCoreApplication.instance().removeNativeEventFilter(self._filter)
        self._window.deleteLater()
