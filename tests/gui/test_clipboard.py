"""M2 WI-13: clipboard writes on the offscreen (in-process) clipboard (F7-1, F7-2; plan D6).

R7 checked at the start of WI-13: offscreen QClipboard keeps text, image data
and "image/png" in-process. The pairing on the real desktop (native CF_DIB /
"PNG" formats) is WI-21 ``test_native_clipboard_formats``.

Pinned here:
- ``set_png`` puts one QMimeData with both an image (``hasImage``) and the
  original PNG bytes under "image/png"; both decode to the source pixels.
- ``set_png`` with bytes that are not a PNG raises ``ValueError`` and leaves
  the clipboard as it was.
- ``apply`` writes ``ClipboardText`` / ``ClipboardPng``, ignores
  ``NoClipboardChange``, and returns whether it changed the clipboard.
"""

import pytest
from PySide6.QtGui import QGuiApplication

from snapocr.actions.outcomes import ClipboardPng, ClipboardText, NoClipboardChange
from snapocr.gui.clipboard import apply, set_png, set_text
from snapocr.gui.imageops import decode_png, encode_png
from support.qimages import gradient, pixels

SENTINEL = "snapocr-sentinel-clipboard"


@pytest.fixture
def clipboard(qapp):
    cb = QGuiApplication.clipboard()
    cb.setText(SENTINEL)
    yield cb
    cb.clear()


def test_set_text_roundtrip(clipboard):
    set_text("识别结果 Hello\n第二行")
    assert clipboard.text() == "识别结果 Hello\n第二行"


def test_set_text_empty_string(clipboard):
    set_text("")
    assert clipboard.text() == ""


def test_set_png_puts_image_and_png_bytes(clipboard):
    src = gradient(17, 11)
    png = encode_png(src)
    set_png(png)
    mime = clipboard.mimeData()
    assert mime.hasImage()
    assert "image/png" in mime.formats()
    assert bytes(mime.data("image/png")) == png
    assert pixels(mime.imageData()) == pixels(src)
    assert pixels(decode_png(bytes(mime.data("image/png")))) == pixels(src)


def test_set_png_replaces_text(clipboard):
    set_png(encode_png(gradient(3, 3)))
    assert clipboard.text() == ""
    assert clipboard.mimeData().hasImage()


def test_set_png_with_garbage_leaves_clipboard_unchanged(clipboard):
    with pytest.raises(ValueError):
        set_png(b"not a png")
    assert clipboard.text() == SENTINEL
    assert not clipboard.mimeData().hasImage()


def test_apply_text(clipboard):
    assert apply(ClipboardText("abc")) is True
    assert clipboard.text() == "abc"


def test_apply_png(clipboard):
    src = gradient(5, 4)
    assert apply(ClipboardPng(encode_png(src))) is True
    assert pixels(clipboard.mimeData().imageData()) == pixels(src)


def test_apply_no_change_keeps_sentinel(clipboard):
    assert apply(NoClipboardChange()) is False
    assert clipboard.text() == SENTINEL


def test_apply_rejects_other_values(clipboard):
    with pytest.raises(TypeError):
        apply("abc")
    assert clipboard.text() == SENTINEL
