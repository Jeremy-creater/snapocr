"""M7 WI-7: "跟随系统" follows a Windows light / dark switch while snapocr runs (PRD F20-3; M7 plan D7).

Pinned here (beyond the plan text):
- The controller listens to ``QStyleHints.colorSchemeChanged`` and takes the
  scheme from the signal (offscreen the scheme itself never changes, so the
  tests emit the signal the way Qt does on a real switch). ``Unknown`` counts
  as light.
- A fixed theme ignores the switch; the remembered scheme still applies when
  the user later saves "跟随系统".
"""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication

from snapocr.commands import Command
from snapocr.theme import PALETTES, Look
from test_controller import clipboard, make  # noqa: F401 (fixtures)
from test_window_theme import FakeGlass, choose, open_settings

DARK, LIGHT, UNKNOWN = Qt.ColorScheme.Dark, Qt.ColorScheme.Light, Qt.ColorScheme.Unknown


@pytest.fixture
def switch():
    hints = QGuiApplication.styleHints()
    yield hints.colorSchemeChanged.emit
    hints.colorSchemeChanged.emit(hints.colorScheme())  # back to what the platform says


def test_system_theme_follows_dark_and_back(make, switch):
    glass = FakeGlass()
    h = make(glass=glass)
    popup = h.controller.popup
    h.controller.run(Command.TRANSLATE_TEXT)
    switch(DARK)
    assert popup.look == Look(PALETTES["dark_glass"], True)
    assert glass.tint == PALETTES["dark_glass"].acrylic
    assert popup.isVisible()
    switch(LIGHT)
    assert popup.look == Look(PALETTES["light_glass"], True)
    switch(DARK)
    switch(UNKNOWN)
    assert popup.look == Look(PALETTES["light_glass"], True)


def test_without_glass_the_switch_picks_the_solid_of_the_same_brightness(make, switch):
    h = make()
    switch(DARK)
    assert h.controller.popup.look == Look(PALETTES["dark_solid"], False)


@pytest.mark.parametrize("theme", ["light_glass", "dark_glass", "light_solid"])
def test_fixed_themes_ignore_the_switch(make, switch, theme):
    h = make(glass=FakeGlass(), theme=theme)
    before = h.controller.popup.look
    switch(DARK)
    assert h.controller.popup.look == before
    switch(LIGHT)
    assert h.controller.popup.look == before


def test_the_switch_is_remembered_for_a_later_save(make, switch):
    h = make(glass=FakeGlass(), theme="light_solid")
    switch(DARK)
    window = open_settings(h)
    choose(window, "system")
    window.save_button.click()
    assert h.controller.popup.look == Look(PALETTES["dark_glass"], True)
