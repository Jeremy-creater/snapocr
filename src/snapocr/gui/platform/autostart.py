"""Start at login through the current user's Run key (PRD F11-6). Needs no admin rights.

Whether start at login is on is only whether the value exists; its command is
written when it is switched on (``snapocr.autostart.autostart_command``).
"""

from __future__ import annotations

import winreg

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "snapocr"


class RegistryAutostart:
    """``set_enabled`` raises ``OSError`` when the registry refuses the change."""

    def __init__(self, command: str, *, key_path: str = RUN_KEY, value_name: str = VALUE_NAME) -> None:
        self._command = command
        self._key_path = key_path
        self._value_name = value_name

    def is_enabled(self) -> bool:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self._key_path) as key:
                winreg.QueryValueEx(key, self._value_name)
        except FileNotFoundError:
            return False
        return True

    def set_enabled(self, enabled: bool) -> None:
        if enabled:
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, self._key_path, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, self._value_name, 0, winreg.REG_SZ, self._command)
            return
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self._key_path, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, self._value_name)
        except FileNotFoundError:
            pass  # key or value missing: already off
