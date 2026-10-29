"""M9 WI-22: start-up and shutdown on the real Mac (gui-mac lane; PRD F23-1, F23-6, F23-8, F5-1, F5-4, F5-5).

Hotkeys are six modifier combinations on F19 from a temporary config, so they
never clash with a snapocr that is really running. The instance lock of a
temporary config is a file in ``$TMPDIR`` named by the hash of that path.

Pinned here:
- ``start(argv)`` uses the Mac kit: accessory activation policy (no Dock
  icon, no app menu), the menu bar icon visible, the six hotkeys registered
  and live, notices shown through it.
- A second ``start`` on the same config is None, its box closes itself.
- ``shutdown()`` frees the hotkeys and the lock; twice is harmless.
- ``main()`` runs the event loop and shuts down; 0 when already running.
- The kit's ``open_file`` opens the default text editor or raises ``OSError``;
  start at login is not there yet and says so.
"""

import ctypes
import subprocess
import sys
import time
from pathlib import Path

import pytest

from snapocr.actions.outcomes import Notice
from snapocr.gui.platform.launch import platform_kit, start
from snapocr.gui.platform.mac import _cocoa as c
from snapocr.gui.platform.mac import kit
from snapocr.gui.platform.mac.hotkeys import CarbonHotkeys
from snapocr.hotkeys import parse_hotkey
from support.mac_input import press_combo

pytestmark = pytest.mark.gui

KEYS = {"capture": "Ctrl+Alt+Shift+F19", "ocr": "Ctrl+Alt+F19", "translate": "Ctrl+Shift+F19",
        "translate_text": "Alt+Shift+F19", "code_ocr": "Ctrl+F19", "table_ocr": "Alt+F19"}


def write_config(path: Path) -> Path:
    lines = ["[hotkeys]"] + [f'{k} = "{v}"' for k, v in KEYS.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


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


def test_the_mac_kit_is_chosen():
    assert platform_kit() is kit


def test_start_is_a_menu_bar_app_with_live_hotkeys(qtbot, running, tmp_path):
    app = running(write_config(tmp_path / "config.local.toml"))
    assert app is not None
    assert c.send(c.ns_app(), "activationPolicy", restype=ctypes.c_long) == c.NSApplicationActivationPolicyAccessory
    assert app.tray.icon.isVisible()
    assert sorted(cmd.value for cmd in app.controller.registered_commands()) == sorted(KEYS)
    hk = parse_hotkey(KEYS["translate_text"])
    press_combo(hk.mods, hk.vk)
    qtbot.waitUntil(lambda: app.controller.popup.isVisible(), timeout=2000)


def test_notices_go_through_the_menu_bar_icon(running, tmp_path):
    app = running(write_config(tmp_path / "config.local.toml"))
    assert app.tray.icon.supportsMessages()
    app.tray.notify(Notice("snapocr gui-mac", "测试通知，可以忽略。"))


def test_config_problems_reach_the_start_up_notice(qtbot, running, tmp_path, monkeypatch):
    from snapocr.gui.platform.tray import Tray

    shown = []
    real_notify = Tray.notify
    monkeypatch.setattr(Tray, "notify", lambda self, n: (shown.append(n), real_notify(self, n)))
    path = tmp_path / "config.local.toml"
    path.write_text(write_config(path).read_text(encoding="utf-8").replace("Ctrl+F19", "Ctrl+Nope"), encoding="utf-8")
    app = running(path)
    assert app is not None
    qtbot.waitUntil(lambda: any(n.title == "配置文件有 1 个问题" for n in shown), timeout=3000)
    (notice,) = [n for n in shown if n.title == "配置文件有 1 个问题"]
    assert "code_ocr" in notice.body and "Nope" in notice.body


def test_a_second_start_on_the_same_config_is_none(running, tmp_path):
    path = write_config(tmp_path / "config.local.toml")
    assert running(path) is not None
    t0 = time.monotonic()
    assert running(path) is None
    assert 2.5 <= time.monotonic() - t0 < 5  # the "已在运行" box closed itself after about 3 s


def test_shutdown_frees_hotkeys_and_lock(running, tmp_path):
    path = write_config(tmp_path / "config.local.toml")
    app = running(path)
    app.shutdown()
    app.shutdown()
    assert not app.tray.icon.isVisible()
    other = CarbonHotkeys()
    try:
        for i, text in enumerate(KEYS.values()):
            hk = parse_hotkey(text)
            assert other.register(100 + i, hk.mods, hk.vk) == 0, text
    finally:
        other.close()
    lock = kit.acquire(path)
    assert lock is not None
    lock.release()


def test_main_runs_until_quit_then_shuts_down(qapp, tmp_path, monkeypatch):
    from PySide6.QtCore import QTimer

    from snapocr.gui.platform.launch import main

    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    path = write_config(tmp_path / "config.local.toml")
    QTimer.singleShot(1500, qapp.quit)
    assert main(["snapocr", "--config", str(path)], log_dir=tmp_path / "logs") == 0
    lock = kit.acquire(path)
    assert lock is not None
    lock.release()


def test_main_returns_0_when_already_running(qapp, tmp_path, monkeypatch):
    from snapocr.gui.platform.launch import main

    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    path = write_config(tmp_path / "config.local.toml")
    held = kit.acquire(path)
    try:
        assert main(["snapocr", "--config", str(path)], log_dir=tmp_path / "logs") == 0
    finally:
        held.release()


def test_acquire_puts_the_lock_where_asked(tmp_path):
    lock = kit.acquire(tmp_path / "a.toml", tmp_path / "locks")
    assert lock is not None
    assert [p.name.startswith("snapocr-") for p in (tmp_path / "locks").iterdir()] == [True]
    assert kit.acquire(tmp_path / "a.toml", tmp_path / "locks") is None
    lock.release()


def test_open_file_of_a_missing_file_is_an_error(tmp_path):
    with pytest.raises(OSError, match="does not exist"):
        kit.open_file(tmp_path / "missing.toml")


def test_open_file_opens_the_default_text_editor(tmp_path):
    path = tmp_path / "snapocr-open-test.toml"
    path.write_text("x = 1\n", encoding="utf-8")
    kit.open_file(path)
    script = f'tell application "TextEdit" to close (every document whose name is "{path.name}") saving no'
    deadline = time.monotonic() + 5
    names = ""
    while time.monotonic() < deadline and path.name not in names:
        names = subprocess.run(["osascript", "-e", 'tell application "TextEdit" to get name of every document'],
                               capture_output=True, text=True).stdout
        time.sleep(0.1)
    subprocess.run(["osascript", "-e", script], check=False)
    assert path.name in names


def test_start_at_login_is_not_there_yet():
    autostart = kit.make_autostart(Path(sys.executable), Path("config.toml"), False)
    assert autostart.is_enabled() is False
    autostart.set_enabled(False)
    with pytest.raises(OSError, match="还不支持开机自启动"):
        autostart.set_enabled(True)


def test_glass_is_solid():
    assert kit.glass().facts().build == 0
