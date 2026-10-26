"""Single instance via a named Win32 mutex (F5-4, plan D5).

The kernel frees the mutex when the process ends, so a crash leaves no stale
lock. The name comes from ``snapocr.config.files.instance_name``.
"""

from __future__ import annotations

import ctypes

from snapocr.gui.platform import _win32


class InstanceLock:
    def __init__(self, handle: int) -> None:
        self._handle = handle

    def release(self) -> None:
        if self._handle:
            _win32.kernel32.CloseHandle(self._handle)
            self._handle = 0


def acquire(name: str) -> InstanceLock | None:
    """The lock for ``name``, or None when another holder (any process) has it."""
    handle = _win32.kernel32.CreateMutexW(None, False, name)
    error = _win32.get_last_error()
    if not handle:
        raise ctypes.WinError(error)
    if error == _win32.ERROR_ALREADY_EXISTS:
        _win32.kernel32.CloseHandle(handle)
        return None
    return InstanceLock(handle)
