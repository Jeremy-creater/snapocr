"""M2 WI-18: application icon (PRD F5-6; plan D8).

``tools/make_icon.py`` is a dev script, not part of the package, so it is not
in the ``snapocr`` coverage figures; these tests still pin its pure parts:

- ``build_ico(entries)`` / ``parse_ico(data)``: an ICO container of PNG
  entries ``(size, png_bytes)``; ``parse_ico(build_ico(e)) == e``. Sizes are
  1..256; anything else, or an empty list, is a ``ValueError``; so is data
  that is not such an ICO.
- ``rounded_rect_alpha(size, rect, radius)``: an antialiased Alpha8 mask;
  0 outside the rounded rect, 255 well inside, never increasing from the
  centre outwards.
- The committed ``snapocr.ico`` has exactly the sizes 16, 24, 32, 48, 256;
  each has transparent corners, an opaque centre, and no whitish
  semi-transparent pixel anywhere (no white fringe, any taskbar colour).
"""

import importlib.util
import struct
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from PySide6.QtGui import QImage

ROOT = Path(__file__).resolve().parents[2]
ICO = ROOT / "src" / "snapocr" / "gui" / "assets" / "snapocr.ico"
PNG_256 = ROOT / "src" / "snapocr" / "gui" / "assets" / "snapocr-256.png"
SIZES = [16, 24, 32, 48, 256]

pytestmark = pytest.mark.usefixtures("qapp")


def _load_tool():
    spec = importlib.util.spec_from_file_location("make_icon", ROOT / "tools" / "make_icon.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


make_icon = _load_tool()


def fake_png(n: int) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + bytes([n % 256]) * (n % 37 + 1)


# --- ICO container ----------------------------------------------------------------


@settings(max_examples=40)
@given(st.lists(st.integers(1, 256), min_size=1, max_size=8, unique=True))
def test_ico_roundtrip(sizes):
    entries = [(s, fake_png(s)) for s in sizes]
    assert make_icon.parse_ico(make_icon.build_ico(entries)) == entries


def test_ico_layout_follows_the_format():
    data = make_icon.build_ico([(16, b"A" * 5), (256, b"B" * 7)])
    assert struct.unpack_from("<HHH", data, 0) == (0, 1, 2)
    w, h, colors, reserved, planes, bpp, size, offset = struct.unpack_from("<BBBBHHII", data, 6)
    assert (w, h, colors, reserved, planes, bpp, size, offset) == (16, 16, 0, 0, 1, 32, 5, 6 + 2 * 16)
    w, h, *_ , size, offset = struct.unpack_from("<BBBBHHII", data, 22)
    assert (w, h, size, offset) == (0, 0, 7, 38 + 5)  # 256 is written as 0
    assert data[38:43] == b"A" * 5 and data[43:] == b"B" * 7


@pytest.mark.parametrize("entries", [[], [(0, b"x")], [(257, b"x")], [(16, b"")]], ids=["empty", "zero", "257", "no-data"])
def test_build_ico_rejects_bad_entries(entries):
    with pytest.raises(ValueError):
        make_icon.build_ico(entries)


@pytest.mark.parametrize("data", [b"", b"\x00\x00\x02\x00\x01\x00" + b"\x00" * 16, b"\x00\x00\x01\x00\x01\x00" + b"\x00" * 10],
                         ids=["empty", "cursor-type", "truncated"])
def test_parse_ico_rejects_garbage(data):
    with pytest.raises(ValueError):
        make_icon.parse_ico(data)


# --- alpha mask ---------------------------------------------------------------------


def alpha_rows(mask: QImage):
    return [[mask.pixelColor(x, y).alpha() for x in range(mask.width())] for y in range(mask.height())]


def test_mask_outside_zero_inside_full():
    mask = make_icon.rounded_rect_alpha((100, 80), (10.0, 10.0, 80.0, 60.0), 15.0)
    a = alpha_rows(mask)
    assert (mask.width(), mask.height()) == (100, 80)
    assert a[0][0] == a[79][99] == a[5][50] == a[40][5] == 0
    assert a[11][11] == 0  # cut off by the corner
    assert a[40][50] == a[12][50] == a[40][12] == 255
    assert 0 < a[10][50] <= 255 or a[10][50] == 255  # edge row is covered (antialiased)


@settings(max_examples=25, deadline=None)
@given(st.integers(20, 120), st.integers(20, 120), st.floats(0, 0.45))
def test_mask_never_increases_away_from_centre(w, h, rfrac):
    radius = rfrac * min(w, h)
    mask = make_icon.rounded_rect_alpha((w + 8, h + 8), (4.0, 4.0, float(w), float(h)), radius)
    a = alpha_rows(mask)
    cx, cy = (w + 8) // 2, (h + 8) // 2
    for y in range(h + 8):  # along each row, outwards from the centre column
        row = a[y]
        assert all(row[x] >= row[x + 1] for x in range(cx, w + 7))
        assert all(row[x] >= row[x - 1] for x in range(cx, 0, -1))
    for x in range(w + 8):
        col = [a[y][x] for y in range(h + 8)]
        assert all(col[y] >= col[y + 1] for y in range(cy, h + 7))
        assert all(col[y] >= col[y - 1] for y in range(cy, 0, -1))
    assert a[cy][cx] == 255 and a[0][0] == 0


# --- committed assets -----------------------------------------------------------------


def _decoded_entries():
    if not ICO.is_file():
        pytest.fail(f"missing {ICO}; regenerate with: python tools/make_icon.py")
    entries = make_icon.parse_ico(ICO.read_bytes())
    return [(size, QImage.fromData(png, "PNG")) for size, png in entries]


def test_ico_has_the_five_sizes():
    assert [size for size, _ in _decoded_entries()] == SIZES


@pytest.mark.parametrize("index", range(len(SIZES)), ids=[str(s) for s in SIZES])
def test_each_size_has_clean_edges(index):
    size, image = _decoded_entries()[index]
    image = image.convertToFormat(QImage.Format.Format_ARGB32)
    assert (image.width(), image.height()) == (size, size)
    corners = [(0, 0), (size - 1, 0), (0, size - 1), (size - 1, size - 1)]
    assert all(image.pixelColor(x, y).alpha() == 0 for x, y in corners)
    assert image.pixelColor(size // 2, size // 2).alpha() == 255
    fringe = []
    for y in range(size):
        for x in range(size):
            c = image.pixelColor(x, y)
            if 0 < c.alpha() < 255 and min(c.red(), c.green(), c.blue()) >= 160:
                fringe.append((x, y, c.getRgb()))
    assert fringe == []


def test_png_256_matches_the_ico_entry():
    if not PNG_256.is_file():
        pytest.fail(f"missing {PNG_256}; regenerate with: python tools/make_icon.py")
    png = QImage(str(PNG_256)).convertToFormat(QImage.Format.Format_ARGB32)
    ico_256 = _decoded_entries()[-1][1].convertToFormat(QImage.Format.Format_ARGB32)
    assert png == ico_256
