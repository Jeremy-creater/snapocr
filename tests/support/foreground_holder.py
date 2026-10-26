"""Helper process for the gui lane (FIX-4): a window from another process that holds the foreground.

Run as a script: shows a small window, forces it to the foreground
(AttachThreadInput + SetForegroundWindow, independent of snapocr's code),
prints its HWND, then waits until a line arrives on stdin.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from PySide6.QtWidgets import QApplication, QLabel

user32 = ctypes.WinDLL("user32")
kernel32 = ctypes.WinDLL("kernel32")
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.c_void_p]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]


def main() -> None:
    app = QApplication(sys.argv[:1])
    label = QLabel("snapocr gui test: foreground holder")
    label.resize(360, 80)
    label.show()
    app.processEvents()
    hwnd = int(label.winId())
    for _ in range(20):
        current = user32.GetForegroundWindow()
        other = user32.GetWindowThreadProcessId(current, None)
        me = kernel32.GetCurrentThreadId()
        user32.AttachThreadInput(me, other, True)
        user32.SetForegroundWindow(hwnd)
        user32.AttachThreadInput(me, other, False)
        app.processEvents()
        if user32.GetForegroundWindow() == hwnd:
            break
    print(hwnd, flush=True)
    sys.stdin.readline()


if __name__ == "__main__":
    main()
