"""In-memory stand-in for the system-wide RegisterHotKey table.

A combination (modifiers without MOD_NOREPEAT, virtual key) can have one owner.
``preoccupy`` marks combinations held by other programs. Return values follow
Win32: 0 on success, otherwise the error code; ``taken_code`` is the code for
a combination that is taken (Carbon's -9878 to stand in for a Mac, M9 WI-7).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from snapocr.hotkeys import MOD_NOREPEAT

ERROR_HOTKEY_ALREADY_REGISTERED = 1409
ERROR_HOTKEY_NOT_REGISTERED = 1419

OTHER_PROGRAM = "other program"


@dataclass
class FakeHotkeyTable:
    owners: dict[tuple[int, int], object] = field(default_factory=dict)
    ours: dict[int, tuple[int, int]] = field(default_factory=dict)  # id -> (mods as passed, vk)
    taken_code: int = ERROR_HOTKEY_ALREADY_REGISTERED

    def preoccupy(self, mods: int, vk: int) -> None:
        self.owners[(mods & ~MOD_NOREPEAT, vk)] = OTHER_PROGRAM

    def register(self, hotkey_id: int, mods: int, vk: int) -> int:
        combo = (mods & ~MOD_NOREPEAT, vk)
        if combo in self.owners or hotkey_id in self.ours:
            return self.taken_code
        self.owners[combo] = hotkey_id
        self.ours[hotkey_id] = (mods, vk)
        return 0

    def unregister(self, hotkey_id: int) -> int:
        if hotkey_id not in self.ours:
            return ERROR_HOTKEY_NOT_REGISTERED
        mods, vk = self.ours.pop(hotkey_id)
        del self.owners[(mods & ~MOD_NOREPEAT, vk)]
        return 0

    def snapshot(self) -> dict[tuple[int, int], object]:
        return dict(self.owners)
