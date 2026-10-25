"""WI-3: structural PNG validation of input bytes (no pixel decoding)."""

import random
import re
import struct
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from snapocr.engines.errors import InvalidImageError, InvalidImageReason
from snapocr.engines.image_check import check_png_bytes
from support.png import PNG_SIGNATURE, chunk, ihdr_payload, make_png, make_png_header, set_ihdr_size

R = InvalidImageReason
DIMS = st.integers(1, 2**31 - 1)


def reject(data: object) -> InvalidImageError:
    with pytest.raises(InvalidImageError) as info:
        check_png_bytes(data)
    return info.value


# --- success -----------------------------------------------------------------


def test_minimal_png_returns_size():
    result = check_png_bytes(make_png(1, 1))
    assert result == (1, 1)
    assert all(type(v) is int for v in result)


def test_bytearray_is_accepted_like_bytes():
    data = make_png(3, 2)
    expected = struct.unpack(">II", data[16:24])
    assert check_png_bytes(data) == expected == (3, 2)
    assert check_png_bytes(bytearray(data)) == expected


# --- guards / failure modes --------------------------------------------------

JPEG_HEAD = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
GIF_HEAD = b"GIF89a\x01\x00\x01\x00\x80\x00\x00"
WRONG_FIRST_CHUNK = PNG_SIGNATURE + chunk(b"IDAT", ihdr_payload(4, 4))


@pytest.mark.parametrize(
    "data",
    [
        pytest.param("C:/shots/a.png", id="str-path"),
        pytest.param("http://127.0.0.1/a.png", id="str-url"),
        pytest.param(Path("a.png"), id="Path"),
        pytest.param(None, id="None"),
        pytest.param(42, id="int"),
        pytest.param(memoryview(make_png(1, 1)), id="memoryview"),
    ],
)
def test_rejects_non_bytes_with_type_name(data):
    err = reject(data)
    assert err.reason is R.NOT_BYTES
    assert type(data).__name__ in str(err)


@pytest.mark.parametrize(
    ("data", "reason", "pattern"),
    [
        pytest.param(b"", R.EMPTY, "empty", id="empty-bytes"),
        pytest.param(bytearray(), R.EMPTY, "empty", id="empty-bytearray"),
        pytest.param(JPEG_HEAD, R.NOT_PNG, "not a PNG", id="jpeg"),
        pytest.param(GIF_HEAD, R.NOT_PNG, "not a PNG", id="gif"),
        pytest.param(b"hello", R.NOT_PNG, "not a PNG", id="hello"),
        pytest.param(PNG_SIGNATURE, R.TRUNCATED, "truncated", id="signature-only"),
        pytest.param(make_png_header(5, 5)[:28], R.TRUNCATED, "truncated", id="signature+20"),
        pytest.param(WRONG_FIRST_CHUNK, R.NOT_PNG, "not a PNG", id="first-chunk-not-IHDR"),
        pytest.param(
            set_ihdr_size(make_png(2, 2), 0, 2), R.NOT_PNG, "invalid IHDR dimensions", id="width-0"
        ),
        pytest.param(
            set_ihdr_size(make_png(2, 2), 2, 0), R.NOT_PNG, "invalid IHDR dimensions", id="height-0"
        ),
    ],
)
def test_rejects_with_reason(data, reason, pattern):
    err = reject(data)
    assert err.reason is reason
    assert re.search(pattern, str(err))


def test_not_bytes_message_does_not_echo_input():
    secret = "C:/Users/someone/private/receipt-2026.png"
    err = reject(secret)
    assert err.reason is R.NOT_BYTES
    assert secret not in str(err)


# --- boundary ----------------------------------------------------------------


def test_truncation_boundary_32_vs_33():
    header = make_png_header(640, 480)
    assert len(header) == 33
    assert reject(header[:32]).reason is R.TRUNCATED
    assert check_png_bytes(header[:33]) == (640, 480)


# --- properties --------------------------------------------------------------


@given(DIMS, DIMS)
def test_header_roundtrip(w, h):
    assert check_png_bytes(make_png_header(w, h)) == (w, h)


@given(DIMS, DIMS, st.binary(max_size=4096))
def test_trailing_bytes_do_not_change_result(w, h, tail):
    header = make_png_header(w, h)
    assert check_png_bytes(header + tail) == check_png_bytes(header)


@given(st.binary(max_size=256).filter(lambda b: not b.startswith(PNG_SIGNATURE)))
def test_non_signature_bytes_rejected(data):
    err = reject(data)
    if data == b"":
        assert err.reason is R.EMPTY
    elif PNG_SIGNATURE.startswith(data):
        assert err.reason in (R.NOT_PNG, R.TRUNCATED)
    else:
        assert err.reason is R.NOT_PNG


@given(DIMS, DIMS, st.integers(0, 32))
def test_short_prefix_never_returns_size(w, h, k):
    err = reject(make_png_header(w, h)[:k])
    if k == 0:
        assert err.reason is R.EMPTY
    elif k <= 7:
        assert err.reason is R.NOT_PNG
    else:
        assert err.reason is R.TRUNCATED


@st.composite
def flipped_headers(draw):
    data = bytearray(make_png_header(draw(DIMS), draw(DIMS)))
    positions = draw(st.lists(st.integers(0, len(data) - 1), min_size=1, max_size=3, unique=True))
    for pos in positions:
        data[pos] ^= draw(st.integers(1, 255))
    return bytes(data)


ANY_INPUT = st.one_of(
    st.binary(max_size=512),
    st.text(max_size=64),
    st.none(),
    st.integers(),
    st.floats(allow_nan=True),
    st.binary(max_size=512).map(bytearray),
    flipped_headers(),
)


@given(ANY_INPUT)
def test_check_is_total(data):
    try:
        result = check_png_bytes(data)
    except InvalidImageError:
        return
    assert type(result) is tuple and len(result) == 2
    w, h = result
    assert type(w) is int and type(h) is int
    assert w > 0 and h > 0


def assert_message_safe(data: bytes, message: str) -> None:
    assert len(message) <= 200
    assert "\\x" not in message
    if len(data) >= 8:
        assert repr(data[:8])[2:-1] not in message


def test_error_message_is_bounded_and_leaks_no_bytes():
    data = random.Random(0).randbytes(10240)
    err = reject(data)
    assert_message_safe(data, str(err))


@given(st.binary(min_size=1, max_size=10240).filter(lambda b: not b.startswith(PNG_SIGNATURE)))
def test_error_message_is_bounded_for_any_garbage(data):
    err = reject(data)
    assert_message_safe(data, str(err))


# --- WI-6: real fixture (moved here from WI-3, needs tests/fixtures/mixed.png) --


def test_fixture_png_returns_size():
    path = Path(__file__).resolve().parent.parent / "fixtures" / "mixed.png"
    data = path.read_bytes()
    expected = struct.unpack(">II", data[16:24])
    assert expected == (900, 200)
    assert check_png_bytes(data) == expected
    assert check_png_bytes(bytearray(data)) == expected
