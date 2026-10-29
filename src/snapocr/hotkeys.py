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
MOD_CMD = MOD_WIN  # on a Mac the Win bit means Command (M9 plan D9)

ERROR_HOTKEY_ALREADY_REGISTERED = 1409  # Win32: another program holds the combination
ERROR_HOTKEY_EXISTS_MAC = -9878  # Carbon eventHotKeyExistsErr

PLATFORMS = ("win32", "darwin")


def check_platform(platform: str) -> str:
    """``platform`` if it is one snapocr runs on (a ``sys.platform`` value), else ValueError."""
    if platform not in PLATFORMS:
        raise ValueError(f"unknown platform {platform!r}; expected one of {PLATFORMS}")
    return platform


class HotkeyError(ValueError):
    def __init__(self, token: str, reason: str) -> None:
        super().__init__(f"{token!r}: {reason}")
        self.token = token
        self.reason = reason


# Canonical names in format order, per platform (M9 plan D9): the Win bit is Cmd on a Mac.
# "Control" is an alias of "Ctrl" and "Option" of "Alt" on both; "Command" of "Cmd".
_MODIFIERS = {
    "win32": (("Ctrl", MOD_CONTROL), ("Alt", MOD_ALT), ("Shift", MOD_SHIFT), ("Win", MOD_WIN)),
    "darwin": (("Ctrl", MOD_CONTROL), ("Alt", MOD_ALT), ("Shift", MOD_SHIFT), ("Cmd", MOD_CMD)),
}
_COMMON_MODS = {"ctrl": MOD_CONTROL, "control": MOD_CONTROL, "alt": MOD_ALT, "option": MOD_ALT, "shift": MOD_SHIFT}
_MOD_BY_NAME = {
    "win32": _COMMON_MODS | {"win": MOD_WIN},
    "darwin": _COMMON_MODS | {"cmd": MOD_CMD, "command": MOD_CMD},
}
_WRONG_PLATFORM = {  # names that belong to the other system
    "win32": dict.fromkeys(("cmd", "command"), "a macOS key; on Windows use Win"),
    "darwin": {"win": "a Windows key; on macOS use Cmd"},
}
_REQUIRED = {"win32": "Ctrl, Alt, Shift, Win", "darwin": "Ctrl, Option, Shift, Cmd"}
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


def parse_hotkey(text: object, *, platform: str = "win32") -> Hotkey:
    """``HotkeyError`` names the offending token; ``ValueError`` for an unknown platform."""
    mod_by_name = _MOD_BY_NAME[check_platform(platform)]
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
        if name in mod_by_name:
            bit = mod_by_name[name]
            if mods & bit:
                raise HotkeyError(token, "modifier given twice")
            mods |= bit
        elif name in _WRONG_PLATFORM[platform]:
            raise HotkeyError(token, _WRONG_PLATFORM[platform][name])
        elif name in _VK_BY_NAME:
            if vk is not None:
                raise HotkeyError(token, "only one non-modifier key is allowed")
            vk = _VK_BY_NAME[name]
            if platform == "darwin" and vk not in _MAC_KEYCODES:
                raise HotkeyError(token, "a Mac keyboard has no such key")
        else:
            raise HotkeyError(token, "unknown key name")
    if vk is None:
        raise HotkeyError(whole, "no main key (e.g. 'Alt+1')")
    if not mods:
        raise HotkeyError(whole, f"at least one modifier ({_REQUIRED[platform]}) is required")
    return Hotkey(mods, vk)


def format_hotkey(hotkey: Hotkey, *, platform: str = "win32") -> str:
    """Config text: Ctrl+Alt+Shift+Win+Key, with Cmd for the Win bit on a Mac; Option is written Alt."""
    names = [name for name, bit in _MODIFIERS[check_platform(platform)] if hotkey.mods & bit]
    return "+".join([*names, _KEY_NAMES[hotkey.vk]])


# Interface text on a Mac (M9 plan D9): ⌃⌥⇧⌘ in the system's order, then the key.
_MAC_SYMBOLS = ((MOD_CONTROL, "⌃"), (MOD_ALT, "⌥"), (MOD_SHIFT, "⇧"), (MOD_CMD, "⌘"))
_MAC_KEY_SYMBOLS = {
    0x25: "←", 0x26: "↑", 0x27: "→", 0x28: "↓", 0x09: "⇥", 0x2E: "⌦",
    0x24: "↖", 0x23: "↘", 0x21: "⇞", 0x22: "⇟",
}


def display_hotkey(hotkey: Hotkey, *, platform: str = "win32") -> str:
    """Interface text: the config text on Windows, ⌃⌥⇧⌘ and the key on a Mac (Qt menus read it back)."""
    if check_platform(platform) == "win32":
        return format_hotkey(hotkey, platform=platform)
    symbols = "".join(symbol for bit, symbol in _MAC_SYMBOLS if hotkey.mods & bit)
    return symbols + _MAC_KEY_SYMBOLS.get(hotkey.vk, _KEY_NAMES[hotkey.vk])


# --- macOS (M9 plan D10) ---------------------------------------------------------------------

# Win32 VK -> Carbon kVK (Events.h): physical key positions on an ANSI keyboard.
# VK_DELETE is the forward delete. A Mac has no Insert, PrintScreen or F21-F24.
_MAC_KEYCODES: dict[int, int] = {
    **dict(zip(map(ord, "ASDFHGZXCVBQWERYT"), [0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07,
                                               0x08, 0x09, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x10, 0x11])),
    **dict(zip(map(ord, "OUIPLJKNM"), [0x1F, 0x20, 0x22, 0x23, 0x25, 0x26, 0x28, 0x2D, 0x2E])),
    **dict(zip(map(ord, "1234567890"), [0x12, 0x13, 0x14, 0x15, 0x17, 0x16, 0x1A, 0x1C, 0x19, 0x1D])),
    **dict(zip(range(0x70, 0x84), [0x7A, 0x78, 0x63, 0x76, 0x60, 0x61, 0x62, 0x64, 0x65, 0x6D,
                                   0x67, 0x6F, 0x69, 0x6B, 0x71, 0x6A, 0x40, 0x4F, 0x50, 0x5A])),  # F1-F20
    0x09: 0x30, 0x20: 0x31, 0x2E: 0x75,  # Tab, Space, Delete (forward)
    0x24: 0x73, 0x23: 0x77, 0x21: 0x74, 0x22: 0x79,  # Home, End, PageUp, PageDown
    0x25: 0x7B, 0x27: 0x7C, 0x28: 0x7D, 0x26: 0x7E,  # Left, Right, Down, Up
}
_VK_BY_MAC_KEYCODE = {code: vk for vk, code in _MAC_KEYCODES.items()}

# Carbon modifier bits: cmdKey, shiftKey, optionKey, controlKey.
_CARBON_MODIFIERS = ((MOD_CMD, 0x0100), (MOD_SHIFT, 0x0200), (MOD_ALT, 0x0800), (MOD_CONTROL, 0x1000))


def mac_keycode(vk: int) -> int | None:
    """The Carbon key code of the key ``vk`` names, or None when a Mac keyboard has no such key."""
    return _MAC_KEYCODES.get(vk)


def vk_from_mac_keycode(code: int) -> int | None:
    """The VK for a Carbon key code, or None when it is not a key a hotkey can use."""
    return _VK_BY_MAC_KEYCODE.get(code)


def carbon_modifiers(mods: int) -> int:
    """``RegisterEventHotKey`` modifiers for MOD_* flags; MOD_NOREPEAT has no Carbon meaning."""
    mods &= ~MOD_NOREPEAT
    if not _is_int(mods) or mods <= 0 or mods & ~_ALL_MODS:
        raise ValueError(f"mods must be a non-empty combination of MOD_* flags, got {mods!r}")
    return sum(bit for mod, bit in _CARBON_MODIFIERS if mods & mod)


def hotkey_taken(code: int, *, platform: str = "win32") -> bool:
    """Whether a registration error means another program already holds the combination."""
    taken = {"win32": ERROR_HOTKEY_ALREADY_REGISTERED, "darwin": ERROR_HOTKEY_EXISTS_MAC}
    return code == taken[check_platform(platform)]


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
    bindings: Mapping[Command, Hotkey], register: Callable[[int, int, int], int], *, platform: str = "win32"
) -> RegistrationReport:
    """Register every binding in ``Command`` order; a failure does not stop the rest (F5-3).

    A failure carries the hotkey as the interface shows it on ``platform``.
    """
    report = RegistrationReport()
    for command in Command:
        if command not in bindings:
            continue
        hotkey = bindings[command]
        hid = hotkey_id(command)
        error = register(hid, hotkey.mods | MOD_NOREPEAT, hotkey.vk)
        if error:
            report.failed.append(HotkeyFailure(command, display_hotkey(hotkey, platform=platform), error))
        else:
            report.registered[hid] = command
    return report


def unregister_all(report: RegistrationReport, unregister: Callable[[int], int]) -> list[int]:
    """Release the hotkeys that were registered (F5-5); returns the ids released without error."""
    return [hid for hid in sorted(report.registered) if unregister(hid) == 0]
