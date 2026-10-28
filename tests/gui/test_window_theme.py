"""M7 WI-6: choosing the window theme in the settings window; the controller applies it (PRD F20-1, F20-2, F20-4).

Pinned here (beyond the plan text):
- The settings window's general group has a "窗口风格" combo box (跟随系统 /
  浅色毛玻璃 / 深色毛玻璃 / 浅色实底, data = the config values) with a note
  label under it. ``set_glass_problem(problem)`` sets why glass cannot be
  used; the note shows ``glass_note`` for the theme chosen in the box now.
- The controller takes a ``Glass`` boundary (default ``NoGlass``: not
  Windows 11, so unit tests see solid looks). It resolves the look at start
  and after a save; when ``Glass.apply`` refuses acrylic, the look falls back
  to solid and the reason is ``GLASS_REFUSED``.
- Offscreen the colour scheme is unknown, which counts as light.
"""

import dataclasses

import pytest
from PySide6.QtCore import QPoint

from snapocr.commands import Command
from snapocr.config.files import load_config_file
from snapocr.config.schema import AppConfig
from snapocr.config.settings import settings_of
from snapocr.gui.boundaries import NoGlass
from snapocr.gui.settings_window import SettingsWindow
from snapocr.theme import GLASS_REFUSED, PALETTES, GlassFacts, Look
from test_controller import clipboard, make  # noqa: F401 (fixtures)

DEFAULTS = settings_of(AppConfig())
OK = GlassFacts(26200, True, False)


@dataclasses.dataclass
class FakeGlass:
    facts_now: GlassFacts = OK
    accept: bool = True
    tint: object = "never applied"  # the acrylic tint the window has now (None: off)

    def facts(self):
        return self.facts_now

    def apply(self, widget, tint):
        if tint is not None and not self.accept:
            return False
        self.tint = tint
        return True


# --- settings window ---------------------------------------------------------------------


@pytest.fixture
def window(qtbot):
    w = SettingsWindow()
    qtbot.addWidget(w)
    w.load(DEFAULTS, False)
    w.show()
    qtbot.waitExposed(w)
    return w


def test_theme_row_in_general(window):
    box = window.theme_box
    assert window.theme_label.text() == "窗口风格"
    assert [box.itemText(i) for i in range(box.count())] == ["跟随系统", "浅色毛玻璃", "深色毛玻璃", "浅色实底"]
    assert [box.itemData(i) for i in range(box.count())] == ["system", "light_glass", "dark_glass", "light_solid"]
    assert box.currentData() == "system"
    assert not window.theme_note.isVisible()


def test_load_shows_and_save_sends_the_theme(window, qtbot):
    window.load(dataclasses.replace(DEFAULTS, theme="dark_glass"), False)
    assert window.theme_box.currentData() == "dark_glass"
    window.theme_box.setCurrentIndex(window.theme_box.findData("light_solid"))
    with qtbot.waitSignal(window.save_requested, timeout=1000) as blocker:
        window.save_button.click()
    assert blocker.args[0] == dataclasses.replace(DEFAULTS, theme="light_solid")


def test_note_follows_the_chosen_theme(window):
    window.set_glass_problem("系统设置里关了透明效果")
    assert window.theme_note.isVisible()
    assert window.theme_note.text() == "系统设置里关了透明效果，毛玻璃改用实底显示。"
    window.theme_box.setCurrentIndex(window.theme_box.findData("light_solid"))
    assert not window.theme_note.isVisible()
    window.theme_box.setCurrentIndex(window.theme_box.findData("dark_glass"))
    assert window.theme_note.isVisible()
    window.set_glass_problem(None)
    assert not window.theme_note.isVisible()


# --- controller ----------------------------------------------------------------------------


def fill_alpha_and_rgb(popup):
    image = popup.grab().toImage()
    c = image.pixelColor(QPoint(9, 130) * popup.grab().devicePixelRatio())
    return (c.red(), c.green(), c.blue()), c.alpha()


def open_settings(h):
    h.controller.run(Command.SETTINGS)
    window = h.controller.settings_window
    h.qtbot.waitExposed(window)
    return window


def choose(window, theme):
    window.theme_box.setCurrentIndex(window.theme_box.findData(theme))


def test_no_glass_gives_the_light_solid_look(make):
    assert NoGlass().facts().build < 22000
    h = make()
    assert h.controller.popup.look == Look(PALETTES["light_solid"], False)


def test_glass_look_at_start_when_the_desktop_allows_it(make):
    glass = FakeGlass()
    h = make(glass=glass)
    popup = h.controller.popup
    assert popup.look == Look(PALETTES["light_glass"], True)
    assert glass.tint == PALETTES["light_glass"].acrylic
    assert fill_alpha_and_rgb(popup)[1] < 255


def test_saving_a_theme_restyles_the_open_window_and_writes_the_file(make):
    glass = FakeGlass()
    h = make(glass=glass)
    popup = h.controller.popup
    h.controller.run(Command.TRANSLATE_TEXT)
    before = fill_alpha_and_rgb(popup)
    window = open_settings(h)
    choose(window, "dark_glass")
    window.save_button.click()
    assert not window.isVisible()
    assert popup.isVisible()
    assert popup.look == Look(PALETTES["dark_glass"], True)
    assert glass.tint == PALETTES["dark_glass"].acrylic
    rgb, _ = fill_alpha_and_rgb(popup)
    assert sum(rgb) < sum(before[0])  # darker now
    assert load_config_file(h.config_path).config.theme == "dark_glass"
    assert 'theme = "dark_glass"' in h.config_path.read_text(encoding="utf-8")

    window = open_settings(h)
    choose(window, "light_solid")
    window.save_button.click()
    assert popup.look == Look(PALETTES["light_solid"], False)
    assert glass.tint is None  # acrylic turned off
    assert fill_alpha_and_rgb(popup)[1] == 255


def test_cancel_keeps_the_look(make):
    h = make(glass=FakeGlass())
    window = open_settings(h)
    choose(window, "dark_glass")
    window.cancel_button.click()
    assert h.controller.popup.look == Look(PALETTES["light_glass"], True)


def test_transparency_off_falls_back_to_solid_and_the_settings_say_why(make):
    h = make(glass=FakeGlass(GlassFacts(26200, False, False)))
    assert h.controller.popup.look == Look(PALETTES["light_solid"], False)
    window = open_settings(h)
    assert window.theme_note.isVisible()
    assert window.theme_note.text() == "系统设置里关了透明效果，毛玻璃改用实底显示。"
    choose(window, "dark_glass")
    window.save_button.click()
    assert h.controller.popup.look == Look(PALETTES["dark_solid"], False)


def test_refused_acrylic_falls_back_to_solid(make):
    h = make(glass=FakeGlass(accept=False))
    assert h.controller.popup.look == Look(PALETTES["light_solid"], False)
    window = open_settings(h)
    assert window.theme_note.text() == f"{GLASS_REFUSED}，毛玻璃改用实底显示。"


def test_theme_from_the_config_at_start(make):
    h = make(glass=FakeGlass(), theme="dark_glass")
    assert h.controller.popup.look == Look(PALETTES["dark_glass"], True)
    assert open_settings(h).theme_box.currentData() == "dark_glass"
