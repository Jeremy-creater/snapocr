"""Global hotkeys (PRD F5-2, F5-3, F5-5) without the Win32 calls. Stdlib only, no ctypes.

``parse_hotkey("Ctrl+Shift+Q")`` gives the ``RegisterHotKey`` modifier mask and
virtual-key code. Tokens are split on ``+``, stripped and matched without case;
only ASCII names count, so look-alikes such as the Kelvin sign are rejected.

``register_all`` / ``unregister_all`` take the RegisterHotKey / UnregisterHotKey
wrappers as arguments, which return 0 or a Win32 error code.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from snapocr.commands import Command

MOD_ALT = 0x1
MOD_CONTROL = 0x2
MOD_SHIFT = 0x4
MOD_WIN = 0x8
MOD_NOREPEAT = 0x4000

ERROR_HOTKEY_ALREADY_REGISTERED = 1409  # Win32: another program holds the combination


class HotkeyError(ValueError):
    def __init__(self, token: str, reason: str) -> None:
        super().__init__(f"{token!r}: {reason}")
        self.token = token
        self.reason = reason


# Canonical names in format order; "Control" is an accepted alias of "Ctrl".
_MODIFIERS = (("Ctrl", MOD_CONTROL), ("Alt", MOD_ALT), ("Shift", MOD_SHIFT), ("Win", MOD_WIN))
_MOD_BY_NAME = {name.lower(): bit for name, bit in _MODIFIERS} | {"control": MOD_CONTROL}
_ALL_MODS = MOD_CONTROL | MOD_ALT | MOD_SHIFT | MOD_WIN

# Win32 virtual-key codes.
_KEY_NAMES: dict[int, str] = {
    **{ord(c): c for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"},
    **{0x6F + n: f"F{n}" for n in range(1, 25)},
    0x20: "Space", 0x09: "Tab", 0x2D: "Insert", 0x2E: "Delete",
    0x24: "Home", 0x23: "End", 0x21: "PageUp", 0x22: "PageDown",
    0x25: "Left", 0x26: "Up", 0x27: "Right", 0x28: "Down", 0x2C: "PrintScreen",
}
_VK_BY_NAME = {name.lower(): vk for vk, name in _KEY_NAMES.items()}


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


@dataclass(frozen=True)
class Hotkey:
    """At least one modifier (MOD_NOREPEAT is added at registration) and a supported key."""

    mods: int
    vk: int

    def __post_init__(self) -> None:
        if not _is_int(self.mods) or not self.mods or self.mods & ~_ALL_MODS:
            raise ValueError(f"mods must be a non-empty combination of MOD_* flags, got {self.mods!r}")
        if not _is_int(self.vk) or self.vk not in _KEY_NAMES:
            raise ValueError(f"unsupported virtual-key code {self.vk!r}")


def parse_hotkey(text: object) -> Hotkey:
    if not isinstance(text, str):
        raise HotkeyError("", f"expected a str like 'Alt+1', got {type(text).__name__}")
    whole = text.strip()
    if not whole:
        raise HotkeyError("", "empty hotkey")
    mods = 0
    vk: int | None = None
    for raw in text.split("+"):
        token = raw.strip()
        if not token:
            raise HotkeyError("", f"empty key name in {whole!r} (stray '+')")
        name = token.lower() if token.isascii() else None
        if name in _MOD_BY_NAME:
            bit = _MOD_BY_NAME[name]
            if mods & bit:
                raise HotkeyError(token, "modifier given twice")
            mods |= bit
        elif name in _VK_BY_NAME:
            if vk is not None:
                raise HotkeyError(token, "only one non-modifier key is allowed")
            vk = _VK_BY_NAME[name]
        else:
            raise HotkeyError(token, "unknown key name")
    if vk is None:
        raise HotkeyError(whole, "no main key (e.g. 'Alt+1')")
    if not mods:
        raise HotkeyError(whole, "at least one modifier (Ctrl, Alt, Shift, Win) is required")
    return Hotkey(mods, vk)


def format_hotkey(hotkey: Hotkey) -> str:
    """Canonical form: Ctrl+Alt+Shift+Win+Key."""
    names = [name for name, bit in _MODIFIERS if hotkey.mods & bit]
    return "+".join([*names, _KEY_NAMES[hotkey.vk]])


def hotkey_id(command: Command) -> int:
    """Stable id passed to RegisterHotKey: the command's position in ``Command``, from 1."""
    return list(Command).index(command) + 1


@dataclass(frozen=True)
class HotkeyFailure:
    command: Command
    hotkey_text: str
    error_code: int


@dataclass
class RegistrationReport:
    registered: dict[int, Command] = field(default_factory=dict)
    failed: list[HotkeyFailure] = field(default_factory=list)


def register_all(
    bindings: Mapping[Command, Hotkey], register: Callable[[int, int, int], int]
) -> RegistrationReport:
    """Register every binding in ``Command`` order; a failure does not stop the rest (F5-3)."""
    report = RegistrationReport()
    for command in Command:
        if command not in bindings:
            continue
        hotkey = bindings[command]
        hid = hotkey_id(command)
        error = register(hid, hotkey.mods | MOD_NOREPEAT, hotkey.vk)
        if error:
            report.failed.append(HotkeyFailure(command, format_hotkey(hotkey), error))
        else:
            report.registered[hid] = command
    return report


def unregister_all(report: RegistrationReport, unregister: Callable[[int], int]) -> list[int]:
    """Release the hotkeys that were registered (F5-5); returns the ids released without error."""
    return [hid for hid in sorted(report.registered) if unregister(hid) == 0]
