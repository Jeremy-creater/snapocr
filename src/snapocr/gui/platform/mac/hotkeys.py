"""Global hotkeys through Carbon ``RegisterEventHotKey`` (PRD F23-2, F5-3, F5-5; M9 plan D10).

The handler sits on the application event target, which Qt's Cocoa event loop
dispatches on the GUI thread. ``register`` / ``unregister`` match the
``HotkeyBackend`` shape that ``snapocr.hotkeys.register_all`` and the
controller use; the key and modifiers arrive as Win32 VK / MOD_* and are
translated here.
"""

from __future__ import annotations

import ctypes

from PySide6.QtCore import QObject, Signal

from snapocr.gui.platform.mac import _cocoa as c
from snapocr.hotkeys import carbon_modifiers, mac_keycode

SIGNATURE = int.from_bytes(b"snap", "big")
paramErr = -50
eventHotKeyInvalidErr = -9879
_APPLICATION = object()  # the default event target, looked up when the backend is made


class CarbonHotkeys(QObject):
    activated = Signal(int)

    def __init__(self, parent: QObject | None = None, *, target=_APPLICATION) -> None:
        super().__init__(parent)
        self._target = c.carbon.GetApplicationEventTarget() if target is _APPLICATION else target
        self._refs: dict[int, ctypes.c_void_p] = {}
        self._proc = c.EventHandlerProcPtr(self._on_event)  # kept alive as long as the handler
        self._handler = ctypes.c_void_p()
        spec = c.EventTypeSpec(c.kEventClassKeyboard, c.kEventHotKeyPressed)
        status = c.carbon.InstallEventHandler(
            self._target, self._proc, 1, ctypes.byref(spec), None, ctypes.byref(self._handler)
        )
        if status != c.noErr:
            raise OSError(f"InstallEventHandler failed: {status}")
        self._closed = False

    def _on_event(self, _call_ref, event, _user_data) -> int:
        hkid = c.EventHotKeyID()
        status = c.carbon.GetEventParameter(
            event, c.kEventParamDirectObject, c.typeEventHotKeyID, None, ctypes.sizeof(hkid), None, ctypes.byref(hkid)
        )
        if status != c.noErr or hkid.signature != SIGNATURE or hkid.id not in self._refs:
            return c.eventNotHandledErr
        self.activated.emit(int(hkid.id))
        return c.noErr

    def register(self, hotkey_id: int, mods: int, vk: int) -> int:
        """0 on success, otherwise the OSStatus (-9878: the combination is taken)."""
        code = mac_keycode(vk)
        if code is None:
            return paramErr
        ref = ctypes.c_void_p()
        status = c.carbon.RegisterEventHotKey(
            code, carbon_modifiers(mods), c.EventHotKeyID(SIGNATURE, hotkey_id),
            self._target, 0, ctypes.byref(ref),
        )
        if status == c.noErr:
            self._refs[hotkey_id] = ref
        return status

    def unregister(self, hotkey_id: int) -> int:
        ref = self._refs.pop(hotkey_id, None)
        if ref is None:
            return eventHotKeyInvalidErr
        return c.carbon.UnregisterEventHotKey(ref)

    def close(self) -> None:
        """Release any hotkey still held and stop listening (F5-5); safe to call twice."""
        if self._closed:
            return
        self._closed = True
        for hotkey_id in list(self._refs):
            self.unregister(hotkey_id)
        c.carbon.RemoveEventHandler(self._handler)
