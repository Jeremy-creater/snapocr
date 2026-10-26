"""M3 WI-3: start at login through the current user's Run key (gui lane; PRD F11-6).

Never touches the real Run key: every test uses ``HKCU\\Software\\snapocr-gui-test\\Run``
and the whole test key is deleted afterwards (CLAUDE.md).

Pinned here:
- ``is_enabled()`` is False when the key or the value is missing.
- ``set_enabled(True)`` creates the key if needed and writes the command as REG_SZ;
  ``set_enabled(False)`` deletes the value and does nothing when it is missing.
- The defaults are the real Run key and the value name ``snapocr``.
"""

import winreg

import pytest

from snapocr.gui.platform.autostart import RUN_KEY, VALUE_NAME, RegistryAutostart

pytestmark = pytest.mark.gui

TEST_ROOT = r"Software\snapocr-gui-test"
TEST_KEY = TEST_ROOT + r"\Run"
COMMAND = r'"D:\envs\snap ocr\pythonw.exe" -m snapocr --config "D:\c.toml"'


def _delete_tree():
    for path in (TEST_KEY, TEST_ROOT):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
        except FileNotFoundError:
            pass


@pytest.fixture
def autostart():
    _delete_tree()
    yield RegistryAutostart(COMMAND, key_path=TEST_KEY, value_name="snapocr-test")
    _delete_tree()


def _value():
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, TEST_KEY) as key:
        return winreg.QueryValueEx(key, "snapocr-test")


def test_defaults():
    assert RUN_KEY == r"Software\Microsoft\Windows\CurrentVersion\Run"
    assert VALUE_NAME == "snapocr"


def test_missing_key_is_disabled_and_disable_is_harmless(autostart):
    assert autostart.is_enabled() is False
    autostart.set_enabled(False)
    assert autostart.is_enabled() is False


def test_enable_creates_key_and_writes_command(autostart):
    autostart.set_enabled(True)
    assert autostart.is_enabled() is True
    assert _value() == (COMMAND, winreg.REG_SZ)


def test_enable_twice_and_disable(autostart):
    autostart.set_enabled(True)
    autostart.set_enabled(True)
    autostart.set_enabled(False)
    assert autostart.is_enabled() is False
    with pytest.raises(FileNotFoundError):
        _value()
    autostart.set_enabled(False)  # value already gone, key still there
    assert autostart.is_enabled() is False


def test_other_values_untouched(autostart):
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, TEST_KEY) as key:
        winreg.SetValueEx(key, "other", 0, winreg.REG_SZ, "keep")
    autostart.set_enabled(True)
    autostart.set_enabled(False)
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, TEST_KEY, 0, winreg.KEY_ALL_ACCESS) as key:
        assert winreg.QueryValueEx(key, "other") == ("keep", winreg.REG_SZ)
        winreg.DeleteValue(key, "other")
