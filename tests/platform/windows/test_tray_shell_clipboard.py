"""M2 WI-21: tray, shell and the native clipboard on the real desktop (gui lane; PRD F5-1, F7-1; plan D6, R7).

Pinned here:
- ``Tray(menu, icon)`` shows a system-tray icon with that context menu and
  tooltip "snapocr"; ``notify(notice)`` shows a tray message (what appears on
  screen is checked by hand, WI-23).
- ``shell.open_file(path)`` opens a file with its default program and raises
  ``OSError`` (FileNotFoundError) for a missing one.
- ``gui.clipboard.set_png`` on the real Windows clipboard offers CF_DIB and
  the registered "PNG" format; both decode to the source pixels. ``set_text``
  offers CF_UNICODETEXT.
- The clipboard keeps the PNG after the process that set it exits, and that
  exit is clean (WI-13 found offscreen Qt segfaulting there).
The user's clipboard is saved before each clipboard test and put back after.
"""

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QSystemTrayIcon

from snapocr.actions.outcomes import Notice
from snapocr.commands import Command
from snapocr.config.schema import DEFAULT_HOTKEYS
from snapocr.gui import clipboard
from snapocr.gui.icons import app_icon
from snapocr.gui.imageops import encode_png
from snapocr.gui.platform import shell
from snapocr.gui.platform.tray import Tray
from snapocr.gui.tray_menu import build_tray_menu
from support import win_clipboard as wc
from support.qimages import gradient, pixels

pytestmark = pytest.mark.gui

TESTS = Path(__file__).resolve().parents[2]


@pytest.fixture
def saved_clipboard(qapp):
    saved = wc.snapshot()
    yield
    wc.restore(saved)


# --- tray (F5-1) ------------------------------------------------------------------


def test_tray_shows_icon_and_menu(qtbot, qapp):
    assert QSystemTrayIcon.isSystemTrayAvailable()
    seen = []
    menu = build_tray_menu(DEFAULT_HOTKEYS, seen.append)
    tray = Tray(menu, app_icon())
    try:
        tray.show()
        assert tray.icon.isVisible()
        qtbot.waitUntil(lambda: not tray.icon.geometry().isEmpty(), timeout=3000)
        assert tray.icon.contextMenu() is menu
        assert tray.icon.toolTip() == "snapocr"
        assert not tray.icon.icon().isNull()
        menu.actions()[1].trigger()
        assert seen == [Command.OCR]
        tray.notify(Notice("snapocr gui 测试", "这条通知来自自动测试，可以忽略。"))
        tray.notify(Notice("snapocr gui 测试", ""))
        tray.notify(Notice("snapocr gui 测试", "警告图标（F18-3）", warning=True))
    finally:
        tray.hide()
    assert not tray.icon.isVisible()


# --- shell ----------------------------------------------------------------------------


def test_open_file_opens_a_toml(tmp_path):
    path = tmp_path / "snapocr-gui-test.toml"
    path.write_text("# opened by the snapocr gui lane; close this window\n", encoding="utf-8")
    shell.open_file(path)


def test_open_missing_file_raises(tmp_path):
    with pytest.raises(OSError):
        shell.open_file(tmp_path / "missing.toml")


# --- native clipboard (F7-1, D6) ---------------------------------------------------------


def test_png_on_the_native_clipboard(qtbot, saved_clipboard):
    src = gradient(37, 23)
    png = encode_png(src)
    clipboard.set_png(png)
    qtbot.wait(100)
    dib = wc.read(wc.CF_DIB)
    native_png = wc.read(wc.PNG)
    assert dib is not None and native_png is not None
    assert pixels(wc.decode_dib(dib)) == pixels(src)
    assert native_png.startswith(png)  # GlobalSize may round the block up
    assert pixels(QImage.fromData(native_png[: len(png)], "PNG")) == pixels(src)


def test_text_on_the_native_clipboard(qtbot, saved_clipboard):
    clipboard.set_text("识别结果 snapocr\n第二行")
    qtbot.wait(100)
    assert wc.read_text() == "识别结果 snapocr\r\n第二行"  # Windows line breaks for other programs


EXITING = textwrap.dedent(
    """
    import sys
    sys.path.insert(0, sys.argv[1])
    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv[:1])
    from snapocr.gui import clipboard
    from snapocr.gui.imageops import encode_png
    from support.qimages import gradient
    clipboard.set_png(encode_png(gradient(19, 11)))
    from snapocr.gui.platform.native_clipboard import flush
    assert flush() == 0  # S_OK; the app does this before quitting (R7)
    print("set", flush=True)
    """
)


def test_png_survives_the_process_exit(qapp, saved_clipboard):
    proc = subprocess.run([sys.executable, "-c", EXITING, str(TESTS)], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "set"
    dib = wc.read(wc.CF_DIB)
    assert dib is not None
    assert pixels(wc.decode_dib(dib)) == pixels(gradient(19, 11))


def test_flushed_png_survives_every_exit(qapp, saved_clipboard):
    """Without the flush about one exit in two lost the clipboard (WI-21); with it, none may."""
    for _ in range(5):
        wc.restore(wc.snapshot())  # take the clipboard back between runs
        proc = subprocess.run([sys.executable, "-c", EXITING, str(TESTS)], capture_output=True, text=True, timeout=60)
        assert proc.returncode == 0, proc.stderr
        dib = wc.read(wc.CF_DIB)
        assert dib is not None
        assert pixels(wc.decode_dib(dib)) == pixels(gradient(19, 11))


def test_flush_in_process_keeps_the_formats(qtbot, saved_clipboard):
    from snapocr.gui.platform.native_clipboard import flush

    png = encode_png(gradient(9, 7))
    clipboard.set_png(png)
    assert flush() == 0
    assert pixels(wc.decode_dib(wc.read(wc.CF_DIB))) == pixels(gradient(9, 7))
    assert wc.read(wc.PNG).startswith(png)
