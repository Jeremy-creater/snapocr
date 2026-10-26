"""M2 WI-13: QImage crop, PNG round trip and thumbnails (F6-2, F7-1, F10-1).

Pinned here:
- ``crop`` takes a box that must lie wholly inside the image (``ValueError``
  otherwise, including empty boxes); the result is a detached copy.
- ``encode_png`` is lossless for opaque RGB32 images; ``decode_png`` rejects
  bytes that are not an image with ``ValueError``.
- ``thumbnail`` has exactly ``fit_size`` dimensions and never enlarges; when no
  scaling is needed it is pixel-identical to the source.
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from PySide6.QtGui import QColor, QImage

from snapocr.geometry import Rect, fit_size
from snapocr.gui.imageops import crop, decode_png, encode_png, thumbnail
from support.qimages import gradient, pixels

pytestmark = pytest.mark.usefixtures("qapp")

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@st.composite
def image_and_box(draw):
    w, h = draw(st.integers(1, 40)), draw(st.integers(1, 30))
    x, y = draw(st.integers(0, w - 1)), draw(st.integers(0, h - 1))
    bw, bh = draw(st.integers(1, w - x)), draw(st.integers(1, h - y))
    return (w, h), Rect(x, y, bw, bh)


def test_crop_example_matches_source_region():
    src = gradient(20, 10)
    out = crop(src, Rect(3, 2, 5, 4))
    assert (out.width(), out.height()) == (5, 4)
    assert pixels(out) == [row[3:8] for row in pixels(src)[2:6]]


@settings(max_examples=30, deadline=None)
@given(image_and_box())
def test_crop_preserves_pixels(spec):
    (w, h), box = spec
    src = gradient(w, h)
    out = crop(src, box)
    assert (out.width(), out.height()) == (box.w, box.h)
    assert pixels(out) == [row[box.x : box.x + box.w] for row in pixels(src)[box.y : box.y + box.h]]


def test_crop_whole_image_is_equal():
    src = gradient(9, 7)
    assert pixels(crop(src, Rect(0, 0, 9, 7))) == pixels(src)


def test_crop_is_detached_from_source():
    src = gradient(6, 6)
    out = crop(src, Rect(0, 0, 3, 3))
    before = pixels(out)
    src.setPixelColor(0, 0, QColor(1, 2, 3))
    assert pixels(out) == before


@pytest.mark.parametrize(
    "box",
    [Rect(-1, 0, 3, 3), Rect(0, -1, 3, 3), Rect(8, 0, 3, 3), Rect(0, 5, 3, 3), Rect(0, 0, 11, 1), Rect(0, 0, 1, 8),
     Rect(0, 0, 0, 3), Rect(0, 0, 3, 0)],
    ids=["left", "top", "right", "bottom", "too-wide", "too-tall", "zero-w", "zero-h"],
)
def test_crop_outside_image_is_rejected(box):
    with pytest.raises(ValueError, match="crop"):
        crop(gradient(10, 7), box)


def test_png_roundtrip_example():
    src = gradient(13, 9)
    data = encode_png(src)
    assert type(data) is bytes
    assert data.startswith(PNG_SIGNATURE)
    assert pixels(decode_png(data)) == pixels(src)


@settings(max_examples=20, deadline=None)
@given(st.integers(1, 48), st.integers(1, 48))
def test_png_roundtrip_is_lossless(w, h):
    src = gradient(w, h)
    assert pixels(decode_png(encode_png(src))) == pixels(src)


@pytest.mark.parametrize("data", [b"", b"not a png", PNG_SIGNATURE + b"\x00" * 8], ids=["empty", "text", "truncated"])
def test_decode_png_rejects_garbage(data):
    with pytest.raises(ValueError, match="PNG"):
        decode_png(data)


def test_encode_png_rejects_null_image():
    with pytest.raises(ValueError, match="empty"):
        encode_png(QImage())


@settings(max_examples=40, deadline=None)
@given(st.integers(1, 300), st.integers(1, 300), st.integers(1, 120), st.integers(1, 120))
def test_thumbnail_size_is_fit_size(w, h, mw, mh):
    out = thumbnail(gradient(w, h) if w * h <= 4000 else QImage(w, h, QImage.Format.Format_RGB32), (mw, mh))
    assert (out.width(), out.height()) == fit_size((w, h), (mw, mh))


def test_thumbnail_without_scaling_is_identical():
    src = gradient(30, 20)
    assert pixels(thumbnail(src, (30, 20))) == pixels(src)
    assert pixels(thumbnail(src, (100, 100))) == pixels(src)


def test_thumbnail_scales_wide_image_by_width():
    out = thumbnail(gradient(200, 50), (100, 100))
    assert (out.width(), out.height()) == (100, 25)


def test_thumbnail_rejects_bad_box():
    with pytest.raises(ValueError):
        thumbnail(gradient(5, 5), (0, 10))


def test_encode_png_failure_raises():
    """libpng refuses images wider than 1,000,000 px; Qt's save() then returns False."""
    wide = QImage(1_000_001, 1, QImage.Format.Format_RGB32)
    wide.fill(0)
    with pytest.raises(ValueError, match="PNG encoding failed"):
        encode_png(wide)
