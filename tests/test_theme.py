"""M7 WI-2: window themes as pure logic (PRD F20-3, F20-4, F20-5; M7 plan D5).

Pinned here (beyond the plan text):
- ``glass_problem`` gives the first reason in the order: not Windows 11
  (build < 22000), transparency effects off, battery saver on.
- ``resolve`` falls back from glass to the solid palette of the same
  brightness; ``dark_solid`` is reached only that way.
- Colours are (r, g, b, a) with 0..255 parts; ``abgr`` packs one for
  ``SetWindowCompositionAttribute`` (0xAABBGGRR).
- Contrast is the WCAG ratio of the colours composited over the window,
  the acrylic tint and a light (white) or dark (#1e1e20) backdrop.
"""

import dataclasses
import itertools

import pytest
from hypothesis import given
from hypothesis import strategies as st

from snapocr.config.schema import THEMES
from snapocr.theme import (
    FONT_FAMILIES,
    PALETTES,
    THEME_LABELS,
    GlassFacts,
    Look,
    abgr,
    contrast,
    font_families,
    glass_note,
    glass_problem,
    over,
    resolve,
    stylesheet,
)

OK = GlassFacts(build=26200, transparency=True, battery_saver=False)


def test_labels_follow_the_config_order():
    assert list(THEME_LABELS) == list(THEMES)
    assert list(THEME_LABELS.values()) == ["跟随系统", "浅色毛玻璃", "深色毛玻璃", "浅色实底"]


def test_palette_names_and_brightness():
    assert set(PALETTES) == {"light_glass", "dark_glass", "light_solid", "dark_solid"}
    for name, p in PALETTES.items():
        assert p.name == name
        assert p.dark == name.startswith("dark")
        assert (p.acrylic is not None) == name.endswith("_glass")


def test_glass_window_lets_the_acrylic_through_solid_is_opaque():
    for name, p in PALETTES.items():
        if name.endswith("_glass"):
            assert 0 < p.window[3] < 255 and 0 < p.acrylic[3] < 255
        else:
            assert p.window[3] == 255


# --- glass_problem --------------------------------------------------------------------


def test_glass_problem_none_when_all_is_well():
    assert glass_problem(OK) is None
    assert glass_problem(dataclasses.replace(OK, build=22000)) is None


@pytest.mark.parametrize(
    ("facts", "reason"),
    [
        (GlassFacts(21999, True, False), "需要 Windows 11"),
        (GlassFacts(19045, False, True), "需要 Windows 11"),
        (GlassFacts(26200, False, False), "系统设置里关了透明效果"),
        (GlassFacts(26200, False, True), "系统设置里关了透明效果"),
        (GlassFacts(26200, True, True), "节电模式开着"),
    ],
)
def test_glass_problem_reasons_in_order(facts, reason):
    assert glass_problem(facts) == reason


# --- resolve ----------------------------------------------------------------------------

CASES = {
    # (theme, dark, problem?) -> (palette, glass)
    ("system", False, False): ("light_glass", True),
    ("system", True, False): ("dark_glass", True),
    ("system", False, True): ("light_solid", False),
    ("system", True, True): ("dark_solid", False),
    ("light_glass", False, False): ("light_glass", True),
    ("light_glass", True, False): ("light_glass", True),
    ("light_glass", False, True): ("light_solid", False),
    ("light_glass", True, True): ("light_solid", False),
    ("dark_glass", False, False): ("dark_glass", True),
    ("dark_glass", True, False): ("dark_glass", True),
    ("dark_glass", False, True): ("dark_solid", False),
    ("dark_glass", True, True): ("dark_solid", False),
    ("light_solid", False, False): ("light_solid", False),
    ("light_solid", True, False): ("light_solid", False),
    ("light_solid", False, True): ("light_solid", False),
    ("light_solid", True, True): ("light_solid", False),
}


def test_cases_cover_every_combination():
    assert set(CASES) == set(itertools.product(THEMES, (False, True), (False, True)))


@pytest.mark.parametrize(("key", "want"), CASES.items(), ids=str)
def test_resolve(key, want):
    theme, dark, broken = key
    look = resolve(theme, dark=dark, problem="节电模式开着" if broken else None)
    assert look == Look(PALETTES[want[0]], want[1])


@pytest.mark.parametrize("theme", ["dark_solid", "", "System", None])
def test_resolve_rejects_unknown_themes(theme):
    with pytest.raises(ValueError):
        resolve(theme, dark=False, problem=None)


# --- glass_note ---------------------------------------------------------------------------


@pytest.mark.parametrize("theme", ["system", "light_glass", "dark_glass"])
def test_glass_note_for_glass_themes(theme):
    assert glass_note(theme, "系统设置里关了透明效果") == "系统设置里关了透明效果，毛玻璃改用实底显示。"
    assert glass_note(theme, None) is None


def test_no_glass_note_for_the_solid_theme():
    assert glass_note("light_solid", "节电模式开着") is None


# --- M9 WI-20: no glass on a Mac (PRD F23-9, F20-4) -----------------------------------------

MAC_SOLID = {"system": ("light_solid", "dark_solid"), "light_glass": ("light_solid", "light_solid"),
             "dark_glass": ("dark_solid", "dark_solid"), "light_solid": ("light_solid", "light_solid")}


def test_glass_facts_default_to_windows():
    assert GlassFacts(26200, True, False).platform == "win32"
    assert glass_problem(GlassFacts(26200, True, False, platform="win32")) is None


@pytest.mark.parametrize("facts", [GlassFacts(0, False, False, platform="darwin"),
                                   GlassFacts(26200, True, False, platform="darwin")])
def test_a_mac_has_no_glass_whatever_else_it_says(facts):
    assert glass_problem(facts) == "macOS 版暂不支持"


@pytest.mark.parametrize("dark", [False, True])
@pytest.mark.parametrize("theme", THEMES)
def test_every_theme_is_solid_on_a_mac(theme, dark):
    problem = glass_problem(GlassFacts(0, False, False, platform="darwin"))
    assert resolve(theme, dark=dark, problem=problem) == Look(PALETTES[MAC_SOLID[theme][dark]], False)
    note = glass_note(theme, problem)
    assert note == (None if theme == "light_solid" else "macOS 版暂不支持，毛玻璃改用实底显示。")


def test_unknown_glass_platform_is_an_error():
    with pytest.raises(ValueError, match="linux"):
        glass_problem(GlassFacts(0, False, False, platform="linux"))


# --- colours -----------------------------------------------------------------------------


def test_abgr_packs_for_win32():
    assert abgr((0xE8, 0xE8, 0xE8, 0x55)) == 0x55E8E8E8
    assert abgr((0x20, 0x24, 0x28, 0x99)) == 0x99282420
    assert abgr((1, 2, 3, 4)) == 0x04030201


def test_over_composites():
    assert over((0, 0, 0, 0), (10, 20, 30)) == (10, 20, 30)
    assert over((255, 255, 255, 255), (10, 20, 30)) == (255, 255, 255)
    assert over((255, 0, 0, 128), (0, 0, 255)) == (128, 0, 127)


def test_contrast_known_values():
    assert contrast((0, 0, 0), (255, 255, 255)) == pytest.approx(21.0)
    assert contrast((255, 255, 255), (255, 255, 255)) == pytest.approx(1.0)
    assert contrast((118, 118, 118), (255, 255, 255)) == pytest.approx(4.54, abs=0.01)


@given(st.tuples(*[st.integers(0, 255)] * 3), st.tuples(*[st.integers(0, 255)] * 3))
def test_contrast_is_symmetric_and_at_least_one(a, b):
    assert contrast(a, b) == pytest.approx(contrast(b, a))
    assert 1.0 <= contrast(a, b) <= 21.0


def backdrop(p):
    base = (30, 30, 32) if p.dark else (255, 255, 255)
    if p.acrylic is not None:
        base = over(p.acrylic, base)
    return over(p.window, base)


TEXT_PAIRS = [
    ("text", "field"),
    ("text", "readonly"),
    ("text", None),
    ("muted", None),
    ("hint", None),
    ("link", None),
    ("segment_text", "segment_track"),
    ("segment_on_text", "segment_on"),
]


@pytest.mark.parametrize("name", sorted(PALETTES))
@pytest.mark.parametrize(("fg", "bg"), TEXT_PAIRS, ids=str)
def test_text_contrast_is_readable(name, fg, bg):
    p = PALETTES[name]
    ground = backdrop(p) if bg is None else over(getattr(p, bg), backdrop(p))
    assert contrast(over(getattr(p, fg), ground), ground) >= 4.5


@pytest.mark.parametrize("name", sorted(PALETTES))
def test_accent_button_text_is_readable(name):
    p = PALETTES[name]
    assert contrast(p.on_accent[:3], p.accent[:3]) >= 4.5


# --- stylesheet ---------------------------------------------------------------------------


def css(c):
    return f"rgba({c[0]}, {c[1]}, {c[2]}, {c[3]})"


@pytest.mark.parametrize("name", sorted(PALETTES))
def test_stylesheet_uses_the_palette(name):
    p = PALETTES[name]
    qss = stylesheet(p)
    for field in ("text", "field", "readonly", "accent", "on_accent", "segment_on", "close_bg", "link"):
        assert css(getattr(p, field)) in qss, field
    for selector in ("#source", "#translation", "#translate", "#close", "#segment", "#title"):
        assert selector in qss


def test_stylesheets_differ_between_palettes():
    assert len({stylesheet(p) for p in PALETTES.values()}) == len(PALETTES)


def test_font_families():
    assert FONT_FAMILIES == ("Segoe UI Variable Text", "Segoe UI", "Microsoft YaHei UI")


def test_font_families_by_platform():
    """M9 WI-4 (plan D21): PingFang first on a Mac, so the main font's line height is the CJK one."""
    assert font_families(".AppleSystemUIFont") == FONT_FAMILIES
    assert font_families(".AppleSystemUIFont", platform="win32") == FONT_FAMILIES
    mac = font_families(".AppleSystemUIFont", platform="darwin")
    assert mac == ("PingFang SC", ".AppleSystemUIFont")
    assert not any("Segoe" in f or "YaHei" in f for f in mac)
    with pytest.raises(ValueError, match="linux"):
        font_families("x", platform="linux")


def test_stylesheet_names_the_font_families():
    """M9 WI-4: a restyle must not put the app's default families back on the text boxes."""
    p = PALETTES["light_solid"]
    assert 'font-family: "Segoe UI Variable Text", "Segoe UI", "Microsoft YaHei UI";' in stylesheet(p)
    mac = stylesheet(p, ("PingFang SC", ".AppleSystemUIFont"))
    assert 'font-family: "PingFang SC", ".AppleSystemUIFont";' in mac
    assert "Segoe" not in mac
