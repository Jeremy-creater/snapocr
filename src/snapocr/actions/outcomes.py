"""What an action hands back to the GUI layer: clipboard content and a notice. Stdlib only."""

from __future__ import annotations

from dataclasses import dataclass

NOTICE_BODY_MAX = 240


def _require(value: object, kind: type, name: str) -> None:
    if type(value) is not kind:
        raise TypeError(f"{name}: expected {kind.__name__}, got {type(value).__name__}")


@dataclass(frozen=True)
class Notice:
    """A tray notice. A body over 240 code points keeps 239 and ends with "…"."""

    title: str
    body: str

    def __post_init__(self) -> None:
        _require(self.title, str, "title")
        _require(self.body, str, "body")
        if len(self.body) > NOTICE_BODY_MAX:
            object.__setattr__(self, "body", self.body[: NOTICE_BODY_MAX - 1] + "…")


@dataclass(frozen=True)
class ClipboardText:
    text: str

    def __post_init__(self) -> None:
        _require(self.text, str, "text")


@dataclass(frozen=True)
class ClipboardPng:
    png: bytes

    def __post_init__(self) -> None:
        _require(self.png, bytes, "png")


@dataclass(frozen=True)
class NoClipboardChange:
    pass


ClipboardAction = ClipboardText | ClipboardPng | NoClipboardChange
