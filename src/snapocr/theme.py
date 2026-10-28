"""Translation-window themes (PRD F20; M7 plan D5). Pure logic, no Qt.

A theme from the config (``[ui] theme``) and two facts about the desktop
(dark mode, whether acrylic can be used) resolve to a ``Look``: one of four
palettes, and whether the window asks Windows for acrylic. ``dark_solid`` is
reached only as the fallback of a dark glass look (F20-4).

Colours are (r, g, b, a) tuples, 0..255. The palettes follow the M7 mock-ups
(A light glass, B dark glass, C light solid); the acrylic tints were tuned on
the real desktop (2026-10-28).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from snapocr.config.schema import THEMES

Color = tuple[int, int, int, int]

FONT_FAMILIES = ("Segoe UI Variable Text", "Segoe UI", "Microsoft YaHei UI")
THEME_LABELS: Mapping[str, str] = MappingProxyType(
    dict(zip(THEMES, ("跟随系统", "浅色毛玻璃", "深色毛玻璃", "浅色实底"), strict=True))
)
WINDOWS_11_BUILD = 22000
GLASS_REFUSED = "系统拒绝了毛玻璃效果"  # Glass.apply returned False


@dataclass(frozen=True)
class Palette:
    name: str
    dark: bool
    window: Color  # the rounded window fill Qt paints
    acrylic: Color | None  # the acrylic tint behind it; None for solid palettes
    border: Color
    text: Color
    muted: Color  # "原文" / "译文" labels
    hint: Color  # the "Ctrl+Enter" hint
    link: Color  # copy buttons
    field: Color  # the source box
    field_border: Color
    focus: Color  # ring round the focused source box
    readonly: Color  # the translation box
    segment_track: Color
    segment_on: Color
    segment_on_text: Color
    segment_text: Color
    accent: Color  # the "翻译" button
    on_accent: Color
    close_bg: Color
    close_fg: Color


def _hex(text: str, alpha: int = 255) -> Color:
    v = int(text.lstrip("#"), 16)
    return (v >> 16 & 0xFF, v >> 8 & 0xFF, v & 0xFF, alpha)


_BLUE = _hex("#0a64c8")
_WHITE = _hex("#ffffff")
_LIGHT_TEXT = dict(text=_hex("#1d1d1f"), muted=_hex("#55555a"), hint=_hex("#5a5a5f"), link=_BLUE,
                   segment_on=_WHITE, segment_on_text=_hex("#1d1d1f"), segment_text=_hex("#3a3a3c"),
                   accent=_BLUE, on_accent=_WHITE, close_fg=_hex("#3a3a3c"), focus=(10, 100, 200, 46))
_DARK_TEXT = dict(text=_hex("#f5f5f7"), muted=_hex("#aeaeb2"), hint=_hex("#a1a1a6"), link=_hex("#64b5ff"),
                  segment_on=_hex("#636366"), segment_on_text=_WHITE, segment_text=_hex("#d1d1d6"),
                  accent=_BLUE, on_accent=_WHITE, close_fg=_hex("#d1d1d6"), focus=(100, 181, 255, 64))

PALETTES: Mapping[str, Palette] = MappingProxyType(
    {
        "light_glass": Palette(
            "light_glass", False, window=(246, 247, 250, 110), acrylic=(232, 232, 232, 0x55),
            border=(255, 255, 255, 150), field=(255, 255, 255, 200), field_border=(0, 0, 0, 16),
            readonly=(255, 255, 255, 115), segment_track=(118, 118, 128, 36), close_bg=(0, 0, 0, 15),
            **_LIGHT_TEXT,
        ),
        "dark_glass": Palette(
            "dark_glass", True, window=(36, 36, 40, 120), acrylic=(32, 36, 40, 0x99),
            border=(255, 255, 255, 31), field=(0, 0, 0, 77), field_border=(255, 255, 255, 20),
            readonly=(0, 0, 0, 46), segment_track=(118, 118, 128, 71), close_bg=(255, 255, 255, 26),
            **_DARK_TEXT,
        ),
        "light_solid": Palette(
            "light_solid", False, window=_hex("#fbfbfd"), acrylic=None,
            border=(0, 0, 0, 26), field=_WHITE, field_border=_hex("#d2d2d7"),
            readonly=_hex("#f2f2f5"), segment_track=_hex("#ececf0"), close_bg=_hex("#efeff2"),
            **_LIGHT_TEXT,
        ),
        "dark_solid": Palette(
            "dark_solid", True, window=_hex("#2c2c2e"), acrylic=None,
            border=(255, 255, 255, 31), field=_hex("#1c1c1e"), field_border=_hex("#3a3a3c"),
            readonly=_hex("#242426"), segment_track=_hex("#3a3a3c"), close_bg=_hex("#3a3a3c"),
            **_DARK_TEXT,
        ),
    }
)


@dataclass(frozen=True)
class GlassFacts:
    """What the desktop says; read by ``snapocr.gui.platform.glass``."""

    build: int  # Windows build number
    transparency: bool  # Settings > Personalisation > Colours > Transparency effects
    battery_saver: bool


@dataclass(frozen=True)
class Look:
    palette: Palette
    glass: bool  # ask Windows for acrylic behind the window


def glass_problem(facts: GlassFacts) -> str | None:
    """F20-4: why acrylic cannot be used, or None."""
    if facts.build < WINDOWS_11_BUILD:
        return "需要 Windows 11"
    if not facts.transparency:
        return "系统设置里关了透明效果"
    if facts.battery_saver:
        return "节电模式开着"
    return None


def resolve(theme: str, *, dark: bool, problem: str | None) -> Look:
    """F20-3, F20-4: the look for ``theme``; ValueError for an unknown theme."""
    if theme not in THEMES:
        raise ValueError(f"unknown theme {theme!r}")
    name = ("dark_glass" if dark else "light_glass") if theme == "system" else theme
    if problem is not None:
        name = name.replace("_glass", "_solid")
    return Look(PALETTES[name], name.endswith("_glass"))


def glass_note(theme: str, problem: str | None) -> str | None:
    """F20-4: the settings-window line under the theme box."""
    if problem is None or theme == "light_solid":
        return None
    return f"{problem}，毛玻璃改用实底显示。"


def abgr(c: Color) -> int:
    """0xAABBGGRR, the colour layout of ``SetWindowCompositionAttribute``."""
    r, g, b, a = c
    return a << 24 | b << 16 | g << 8 | r


def over(fg: Color, bg: tuple[int, ...]) -> tuple[int, int, int]:
    """``fg`` composited over the opaque ``bg`` (source-over, rounded)."""
    a = fg[3] / 255
    return tuple(round(f * a + b * (1 - a)) for f, b in zip(fg[:3], bg[:3], strict=True))


def _luminance(c: tuple[int, ...]) -> float:
    def channel(v: int) -> float:
        s = v / 255
        return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(v) for v in c[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: tuple[int, ...], b: tuple[int, ...]) -> float:
    """WCAG 2 contrast ratio of two opaque colours."""
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _css(c: Color) -> str:
    return f"rgba({c[0]}, {c[1]}, {c[2]}, {c[3]})"


def stylesheet(p: Palette) -> str:
    """The translation window's QSS (object names set in ``snapocr.gui.popup``)."""
    skip = ("name", "dark", "acrylic")
    c = {name: _css(getattr(p, name)) for name in Palette.__dataclass_fields__ if name not in skip}
    return f"""
QWidget {{ color: {c['text']}; }}
QLabel#title {{ font-size: 13px; font-weight: 600; background: transparent; }}
QLabel#muted {{ font-size: 12px; color: {c['muted']}; background: transparent; }}
QLabel#hint {{ font-size: 11px; color: {c['hint']}; background: transparent; }}
QPushButton#close {{ border: none; border-radius: 14px; background: {c['close_bg']}; color: {c['close_fg']}; }}
QPushButton#copy {{ border: none; border-radius: 6px; background: transparent; color: {c['link']};
    font-size: 12px; padding: 0 6px; }}
QPushButton#copy:disabled {{ color: {c['muted']}; }}
QPlainTextEdit#source {{ border: 1px solid {c['field_border']}; border-radius: 10px; background: {c['field']};
    padding: 6px 8px; font-size: 14px; selection-background-color: {c['accent']}; }}
QPlainTextEdit#source:focus {{ border: 2px solid {c['focus']}; }}
QPlainTextEdit#translation {{ border: none; border-radius: 10px; background: {c['readonly']};
    padding: 6px 8px; font-size: 14px; selection-background-color: {c['accent']}; }}
QWidget#segment {{ border-radius: 8px; background: {c['segment_track']}; }}
QWidget#segment QPushButton {{ border: none; border-radius: 6px; background: transparent;
    color: {c['segment_text']}; font-size: 12px; padding: 0 14px; min-height: 26px; }}
QWidget#segment QPushButton:checked {{ background: {c['segment_on']}; color: {c['segment_on_text']};
    font-weight: 600; }}
QPushButton#translate {{ border: none; border-radius: 15px; background: {c['accent']}; color: {c['on_accent']};
    font-size: 13px; font-weight: 600; padding: 0 20px; min-height: 30px; }}
QPushButton#translate:disabled {{ background: {c['segment_track']}; }}
QScrollBar:vertical {{ width: 8px; background: transparent; margin: 6px 2px 6px 0; }}
QScrollBar::handle:vertical {{ background: {c['segment_track']}; border-radius: 3px; min-height: 24px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
"""
