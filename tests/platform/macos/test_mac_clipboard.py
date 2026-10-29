"""M9 WI-21: the real Mac pasteboard (gui-mac lane; PRD F23-9, F7-1, F7-2).

Pinned here:
- ``gui.clipboard.set_png`` on the Mac offers the image as TIFF (``public.tiff``,
  which Qt writes for the image); other programs ask for PNG and the system
  converts it (``«class PNGf»`` in ``clipboard info``). Pixels are unchanged.
- The image stays on the pasteboard after the process that put it there exits,
  every time, with ``kit.flush_clipboard()`` doing nothing (found in WI-21:
  five exits out of five; the Windows flush has no Mac counterpart).
- Text goes in as ``public.utf8-plain-text`` with ``\\n`` line breaks.

The user's clipboard is saved before each test and put back after.
"""

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from PySide6.QtGui import QImage

from snapocr.gui import clipboard
from snapocr.gui.imageops import encode_png
from snapocr.gui.platform.mac import kit
from support import mac_clipboard as mc
from support.qimages import gradient, pixels

pytestmark = pytest.mark.gui

TESTS = Path(__file__).resolve().parents[2]
TIFF = "public.tiff"


@pytest.fixture
def saved_clipboard(qapp):
    saved = mc.snapshot()
    yield
    mc.restore(saved)


def png_from_osascript() -> QImage:
    """What another program gets when it asks for PNG."""
    out = subprocess.run(["osascript", "-e", "the clipboard as «class PNGf»"], capture_output=True, text=True,
                         timeout=10).stdout.strip()
    assert out.startswith("«data PNGf") and out.endswith("»"), out[:80]
    return QImage.fromData(bytes.fromhex(out[len("«data PNGf"):-1]), "PNG")


def test_png_on_the_pasteboard(qtbot, saved_clipboard):
    src = gradient(37, 23)
    clipboard.set_png(encode_png(src))
    qtbot.wait(100)
    assert TIFF in mc.types()
    assert pixels(QImage.fromData(mc.read(TIFF))) == pixels(src)
    info = subprocess.run(["osascript", "-e", "clipboard info"], capture_output=True, text=True, timeout=10).stdout
    assert "«class PNGf»" in info
    assert pixels(png_from_osascript()) == pixels(src)


def test_text_on_the_pasteboard(qtbot, saved_clipboard):
    clipboard.set_text("识别结果 snapocr\n第二行")
    qtbot.wait(100)
    assert mc.read("public.utf8-plain-text").decode() == "识别结果 snapocr\n第二行"


EXITING = textwrap.dedent(
    """
    import sys
    sys.path.insert(0, sys.argv[1])
    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv[:1])
    from snapocr.gui import clipboard
    from snapocr.gui.imageops import encode_png
    from snapocr.gui.platform.mac import kit
    from support.qimages import gradient
    clipboard.set_png(encode_png(gradient(19, 11)))
    kit.flush_clipboard()  # what RunningApp.shutdown does before the process ends (F7-1)
    print("set", flush=True)
    """
)


def test_png_survives_every_exit(qapp, saved_clipboard):
    for _ in range(5):
        mc.restore([[("public.utf8-plain-text", b"snapocr gui-mac marker")]])  # not the image any more
        proc = subprocess.run([sys.executable, "-c", EXITING, str(TESTS)], capture_output=True, text=True, timeout=60)
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.strip() == "set"
        assert pixels(QImage.fromData(mc.read(TIFF))) == pixels(gradient(19, 11))
        image = png_from_osascript()
        assert (image.width(), image.height()) == (19, 11)


def test_snapshot_and_restore_keep_the_users_clipboard(qapp, saved_clipboard):
    """The helper the tests rely on: two items with two types each come back as they were."""
    two = [[("public.utf8-plain-text", b"one"), ("public.html", b"<b>one</b>")],
           [("public.utf8-plain-text", b"two"), ("public.html", b"<b>two</b>")]]
    mc.restore(two)
    assert mc.snapshot() == two
    mc.restore([])
    assert mc.snapshot() == []
    assert kit.flush_clipboard() is None
