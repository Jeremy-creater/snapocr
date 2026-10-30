"""M7 WI-3: acrylic behind the translation window (gui lane; PRD F20-4; M7 plan D4, D6).

Pinned here:
- ``read_facts()`` reads the Windows build, ``EnableTransparency`` under the
  Personalize key (missing value or key: on, the Windows default) and the
  battery-saver bit of ``GetSystemPowerStatus``.
- ``set_acrylic(hwnd, tint)`` turns acrylic on with the 0xAABBGGRR tint, or
  off for ``None``; it returns whether Windows took it. Windows refuses to
  read the accent back (``GetWindowCompositionAttribute`` fails with error 87,
  measured 2026-10-28), so the real state is checked on screen: a transparent
  window over a magenta one shows magenta without acrylic and the tint with it.
- Tests only write the test key ``HKCU\\Software\\snapocr-gui-test\\Personalize``
  and delete it afterwards.
"""

import ctypes
import sys
import winreg

import pytest
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import QWidget

from snapocr.gui.platform import _win32
from snapocr.geometry import Rect
from snapocr.gui.platform.capture import _blit
from snapocr.gui.platform.glass import PERSONALIZE_KEY, NativeGlass, read_facts, set_acrylic
from snapocr.theme import PALETTES, GlassFacts

pytestmark = pytest.mark.gui

TEST_KEY = r"Software\snapocr-gui-test\Personalize"


@pytest.fixture
def test_key():
    key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, TEST_KEY)
    yield key
    key.Close()
    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, TEST_KEY)
    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, r"Software\snapocr-gui-test")


def battery_saver_now():
    status = _win32.SYSTEM_POWER_STATUS()
    assert _win32.kernel32.GetSystemPowerStatus(ctypes.byref(status))
    return status.SystemStatusFlag == 1


def test_facts_of_this_desktop():
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, PERSONALIZE_KEY) as key:
        transparency = winreg.QueryValueEx(key, "EnableTransparency")[0] != 0
    assert read_facts() == GlassFacts(sys.getwindowsversion().build, transparency, battery_saver_now())


@pytest.mark.parametrize(("value", "on"), [(0, False), (1, True)])
def test_transparency_value(test_key, value, on):
    winreg.SetValueEx(test_key, "EnableTransparency", 0, winreg.REG_DWORD, value)
    assert read_facts(key_path=TEST_KEY).transparency is on


def test_transparency_missing_value_is_on(test_key):
    assert read_facts(key_path=TEST_KEY).transparency is True


def test_transparency_missing_key_is_on():
    assert read_facts(key_path=r"Software\snapocr-gui-test\does-not-exist").transparency is True


MAGENTA = (255, 0, 255)
GEOMETRY = QRect(160, 160, 240, 160)  # logical, on the primary screen


def frameless(qtbot, *, translucent):
    w = QWidget(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
    qtbot.addWidget(w)
    if translucent:
        w.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)  # paints nothing: only acrylic shows
    else:
        w.setAutoFillBackground(True)
        palette = w.palette()
        palette.setColor(w.backgroundRole(), QColor(*MAGENTA))
        w.setPalette(palette)
    w.setGeometry(QGuiApplication.primaryScreen().availableGeometry().topLeft().x() + GEOMETRY.x(),
                  QGuiApplication.primaryScreen().availableGeometry().topLeft().y() + GEOMETRY.y(),
                  GEOMETRY.width(), GEOMETRY.height())
    w.show()
    return w


@pytest.fixture
def window(qtbot):
    back = frameless(qtbot, translucent=False)
    front = frameless(qtbot, translucent=True)
    qtbot.waitExposed(front)
    front.back = back
    return front


def centre_colour(qtbot, w):
    qtbot.wait(400)  # let DWM compose
    dpr = w.devicePixelRatio()
    c = w.geometry().center()
    image = _blit(Rect(round(c.x() * dpr), round(c.y() * dpr), 1, 1))
    pixel = image.pixelColor(0, 0)
    return (pixel.red(), pixel.green(), pixel.blue())


def test_acrylic_on_and_off(qtbot, window):
    hwnd = int(window.winId())
    assert centre_colour(qtbot, window) == MAGENTA
    assert set_acrylic(hwnd, 0xF0282420) is True
    r, g, b = centre_colour(qtbot, window)
    assert r < 160 and b < 160  # the dark tint covers the magenta
    assert set_acrylic(hwnd, None) is True
    assert centre_colour(qtbot, window) == MAGENTA


def test_native_glass_applies_a_palette_tint(qtbot, window):
    glass = NativeGlass()
    assert glass.facts() == read_facts()
    assert glass.apply(window, PALETTES["dark_glass"].acrylic) is True
    assert centre_colour(qtbot, window) != MAGENTA
    assert glass.apply(window, None) is True
    assert centre_colour(qtbot, window) == MAGENTA


def test_a_window_that_does_not_exist_is_refused():
    assert set_acrylic(0x7FFF0, 0x55E8E8E8) is False
