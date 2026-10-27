"""M2 WI-22: start-up and shutdown on the real desktop (gui lane; PRD F5-1, F5-4, F5-5, F9-1, F9-2).

Hotkeys here are Ctrl+Alt+Shift+F21..F24 from a temporary config, so they
never clash with a snapocr that is really running. One test starts from a
missing config file and therefore briefly registers the default Alt+1..4.

Pinned here:
- ``start(argv)`` returns a ``RunningApp`` with the tray visible, the
  configured hotkeys registered and live, and a missing config file created
  from the template (F9-1, F9-2).
- A second process on the same config exits with code 0 within 5 s without
  registering anything; its notice box closes itself after 3 s (F5-4). The
  first instance keeps working.
- ``shutdown()`` releases everything: the same combinations can be registered
  again (F5-5); calling it twice is harmless.
- ``start`` returns None (and shows the box) when another instance holds the lock.
"""

import ctypes
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

import pytest

from snapocr.config.files import instance_name
from snapocr.config.template import DEFAULT_TEMPLATE
from snapocr.gui.platform.launch import start
from snapocr.gui.platform.single_instance import acquire
from snapocr.hotkeys import parse_hotkey
from support.win_input import press_combo, register_raw, unregister_raw

pytestmark = pytest.mark.gui

KEYS = {"capture": "Ctrl+Alt+Shift+F21", "ocr": "Ctrl+Alt+Shift+F22", "translate": "Ctrl+Alt+Shift+F23",
        "last_result": "Ctrl+Alt+Shift+F24", "code_ocr": "Ctrl+Alt+Shift+F17",
        "table_ocr": "Ctrl+Alt+Shift+F18"}
HISTORY_TITLE = "snapocr 上次结果"

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
_user32.FindWindowW.restype = wintypes.HWND
_user32.IsWindowVisible.argtypes = [wintypes.HWND]
_user32.IsWindowVisible.restype = wintypes.BOOL


def write_config(path: Path) -> Path:
    lines = ["[hotkeys]"] + [f'{k} = "{v}"' for k, v in KEYS.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def history_window_visible() -> bool:
    hwnd = _user32.FindWindowW(None, HISTORY_TITLE)
    return bool(hwnd) and bool(_user32.IsWindowVisible(hwnd))


@pytest.fixture
def running(qapp, tmp_path):
    apps = []

    def launch(config: Path):
        app = start(["snapocr", "--config", str(config)])
        apps.append(app)
        return app

    yield launch
    for app in apps:
        if app is not None:
            app.shutdown()


def test_start_shows_tray_and_registers_live_hotkeys(qtbot, running, tmp_path):
    app = running(write_config(tmp_path / "config.local.toml"))
    assert app is not None
    assert app.tray.icon.isVisible()
    assert sorted(c.value for c in app.controller.registered_commands()) == sorted(KEYS)
    hk = parse_hotkey(KEYS["last_result"])
    press_combo(hk.mods, hk.vk)
    qtbot.waitUntil(lambda: app.controller.history_window.isVisible(), timeout=2000)


def test_missing_config_is_created_from_the_template(running, tmp_path):
    path = tmp_path / "config.local.toml"
    app = running(path)
    assert app is not None
    assert path.read_text(encoding="utf-8") == DEFAULT_TEMPLATE


def test_shutdown_frees_hotkeys_and_lock(running, tmp_path):
    path = write_config(tmp_path / "config.local.toml")
    app = running(path)
    app.shutdown()
    app.shutdown()
    assert not app.tray.icon.isVisible()
    for text in KEYS.values():
        hk = parse_hotkey(text)
        assert register_raw(hk.mods, hk.vk)
        assert unregister_raw()
    lock = acquire(instance_name(path))
    assert lock is not None
    lock.release()


def test_start_returns_none_when_another_instance_holds_the_lock(qtbot, running, tmp_path):
    path = write_config(tmp_path / "config.local.toml")
    held = acquire(instance_name(path))
    try:
        t0 = time.monotonic()
        assert running(path) is None
        assert 2.5 <= time.monotonic() - t0 < 5  # the notice box closed itself after about 3 s
        hk = parse_hotkey(KEYS["capture"])
        assert register_raw(hk.mods, hk.vk)  # the refused start registered nothing
        assert unregister_raw()
    finally:
        held.release()


def test_second_process_exits_and_the_first_keeps_working(tmp_path):
    path = write_config(tmp_path / "config.local.toml")
    cmd = [sys.executable, "-m", "snapocr", "--config", str(path)]
    first = subprocess.Popen(cmd)
    try:
        deadline = time.monotonic() + 15
        while acquire_probe(path) and time.monotonic() < deadline:  # wait until the first holds the lock
            time.sleep(0.1)
        time.sleep(1.0)  # and has registered its hotkeys
        t0 = time.monotonic()
        second = subprocess.run(cmd, timeout=10)
        assert second.returncode == 0
        assert time.monotonic() - t0 < 5
        assert first.poll() is None
        hk = parse_hotkey(KEYS["last_result"])
        press_combo(hk.mods, hk.vk)
        deadline = time.monotonic() + 3
        while not history_window_visible() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert history_window_visible()
    finally:
        first.terminate()
        first.wait(10)


def acquire_probe(path: Path) -> bool:
    """True while nobody holds the instance lock for ``path``."""
    lock = acquire(instance_name(path))
    if lock is None:
        return False
    lock.release()
    return True


# --- main() in-process (covers the event loop path) --------------------------------------


def test_main_runs_until_quit_then_shuts_down(qapp, tmp_path, monkeypatch):
    from PySide6.QtCore import QTimer

    from snapocr.gui.platform.launch import main

    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    path = write_config(tmp_path / "config.local.toml")
    QTimer.singleShot(1500, qapp.quit)
    assert main(["snapocr", "--config", str(path)], log_dir=tmp_path / "logs") == 0
    hk = parse_hotkey(KEYS["capture"])
    assert register_raw(hk.mods, hk.vk)  # released by shutdown
    assert unregister_raw()
    lock = acquire(instance_name(path))
    assert lock is not None
    lock.release()


def test_main_returns_0_when_already_running(qapp, tmp_path, monkeypatch):
    from snapocr.gui.platform.launch import main

    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    path = write_config(tmp_path / "config.local.toml")
    held = acquire(instance_name(path))
    try:
        assert main(["snapocr", "--config", str(path)], log_dir=tmp_path / "logs") == 0
    finally:
        held.release()
