"""M9 WI-14: Carbon global hotkeys on the real Mac desktop (gui-mac lane; PRD F23-2, F5-3, F5-5).

Run: ``python -m pytest -m "gui and not perf" --qt-desktop ...`` (CLAUDE.md). The
combinations here are Ctrl+Option+Shift+F17..F19, which nothing else uses.

Pinned here:
- ``CarbonHotkeys.register / unregister`` return 0 or the OSStatus; a
  combination already held (here by ourselves under another id) is -9878.
- A registered combination pressed anywhere emits ``activated(id)`` on the
  GUI thread; after ``unregister`` it emits nothing.
- ``close()`` twice is fine, and afterwards the combinations are free again.
- A combination another process holds still registers (0), and one press
  reaches both processes (measured 2026-10-30). So on a Mac a clash with
  another app gives no "taken" notice; Carbon offers no way to see it.
"""

import subprocess
import sys
import threading
from pathlib import Path

import pytest

from snapocr.gui.platform.mac.hotkeys import CarbonHotkeys
from snapocr.hotkeys import ERROR_HOTKEY_EXISTS_MAC, MOD_NOREPEAT, parse_hotkey
from support.mac_input import press_combo

pytestmark = pytest.mark.gui

F19 = parse_hotkey("Ctrl+Alt+Shift+F19")
F18 = parse_hotkey("Ctrl+Alt+Shift+F18")
MAIN = threading.main_thread().ident


@pytest.fixture
def carbon(qapp):
    hk = CarbonHotkeys()
    yield hk
    hk.close()


def test_register_and_activate(qtbot, carbon):
    seen = []
    carbon.activated.connect(lambda i: seen.append((i, threading.get_ident())))
    assert carbon.register(41, F19.mods | MOD_NOREPEAT, F19.vk) == 0
    try:
        with qtbot.waitSignal(carbon.activated, timeout=2000) as blocker:
            press_combo(F19.mods, F19.vk)
        assert blocker.args == [41]
        assert seen == [(41, MAIN)]
    finally:
        assert carbon.unregister(41) == 0


def test_same_combination_twice_is_taken(carbon):
    assert carbon.register(41, F19.mods, F19.vk) == 0
    try:
        assert carbon.register(42, F19.mods, F19.vk) == ERROR_HOTKEY_EXISTS_MAC
    finally:
        carbon.unregister(41)


def test_unregistered_combination_is_silent(qtbot, carbon):
    seen = []
    carbon.activated.connect(seen.append)
    assert carbon.register(43, F18.mods, F18.vk) == 0
    assert carbon.unregister(43) == 0
    press_combo(F18.mods, F18.vk)
    qtbot.wait(500)
    assert seen == []


def test_unregister_unknown_id_reports_error(carbon):
    assert carbon.unregister(4242) != 0


def test_key_a_mac_does_not_have_reports_error(carbon):
    assert carbon.register(44, F19.mods, parse_hotkey("Ctrl+F24").vk) != 0


def test_close_twice_and_the_combination_is_free_again(qapp, carbon):
    assert carbon.register(45, F19.mods, F19.vk) == 0
    carbon.close()
    carbon.close()
    other = CarbonHotkeys()
    try:
        assert other.register(46, F19.mods, F19.vk) == 0
        assert other.unregister(46) == 0
    finally:
        other.close()


def test_a_bad_event_target_is_an_error(qapp):
    with pytest.raises(OSError, match="InstallEventHandler failed"):
        CarbonHotkeys(target=None)


def test_another_backends_hotkey_is_not_ours(qtbot, carbon):
    """Both handlers sit on the application target; each lets the other's events pass.

    Carbon calls the handler installed last first, so ``other`` sees the press
    of ``carbon``'s hotkey before ``carbon`` does and has to pass it on.
    """
    other = CarbonHotkeys()
    mine, theirs = [], []
    carbon.activated.connect(mine.append)
    other.activated.connect(theirs.append)
    try:
        assert carbon.register(47, F19.mods, F19.vk) == 0
        with qtbot.waitSignal(carbon.activated, timeout=2000):
            press_combo(F19.mods, F19.vk)
        qtbot.wait(100)
        assert (mine, theirs) == ([47], [])
    finally:
        other.close()


def test_a_combination_another_process_holds_still_registers_and_both_fire(qtbot, carbon):
    holder_script = Path(__file__).resolve().parents[2] / "support" / "mac_hotkey_holder.py"
    holder = subprocess.Popen([sys.executable, str(holder_script), "Ctrl+Option+Shift+F19", "5"],
                              stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().split() == ["REGISTERED", "0"]
        assert carbon.register(48, F19.mods, F19.vk) == 0  # no -9878 across processes
        with qtbot.waitSignal(carbon.activated, timeout=2000) as got:
            press_combo(F19.mods, F19.vk)
        assert got.args == [48]
        assert holder.stdout.readline().strip() == "FIRED"  # the other process got the same press
    finally:
        holder.kill()
        holder.wait()
