"""What an action hands back to the GUI layer: clipboard content and a notice. Stdlib only."""

from __future__ import annotations

from dataclasses import dataclass

NOTICE_BODY_MAX = 240


def _require(value: object, kind: type, name: str) -> None:
    if type(value) is not kind:
        raise TypeError(f"{name}: expected {kind.__name__}, got {type(value).__name__}")


@dataclass(frozen=True)
class Notice:
    """A tray notice. A body over 240 code points keeps 239 and ends with "…".

    ``warning`` marks a failure: the tray shows it with the warning icon (F18-3).
    """

    title: str
    body: str
    warning: bool = False

    def __post_init__(self) -> None:
        _require(self.title, str, "title")
        _require(self.body, str, "body")
        _require(self.warning, bool, "warning")
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
class ClipboardTable:
    """F16-2: a table as Markdown text and as HTML; both go on the clipboard."""

    markdown: str
    html: str

    def __post_init__(self) -> None:
        _require(self.markdown, str, "markdown")
        _require(self.html, str, "html")


@dataclass(frozen=True)
class NoClipboardChange:
    pass


ClipboardAction = ClipboardText | ClipboardPng | ClipboardTable | NoClipboardChange


@dataclass(frozen=True)
class HistoryRecord:
    """One entry of "last results" (F7-6, F10). ``raw`` is layout-only text (plan A1)."""

    png: bytes
    raw: str
    text: str
    translation: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class Outcome:
    clipboard: ClipboardAction
    notice: Notice | None
    record: HistoryRecord | None


# Popup states (F8).
@dataclass(frozen=True)
class Translating:
    source: str


@dataclass(frozen=True)
class Done:
    source: str
    translation: str


@dataclass(frozen=True)
class Failed:
    source: str
    message: str


PopupState = Translating | Done | Failed


@dataclass(frozen=True)
class OcrStage:
    """OCR finished with text; translation comes next."""

    png: bytes
    raw: str
    text: str


@dataclass(frozen=True)
class TranslateOutcome:
    clipboard: ClipboardAction
    popup: Done | Failed
    record: HistoryRecord | None  # None for typed text (F19-5)
