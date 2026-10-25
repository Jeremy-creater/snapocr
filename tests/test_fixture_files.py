"""WI-9 / R7: format of the committed OCR sample files (unit lane)."""

from pathlib import Path

import pytest

from snapocr.metrics import normalize_for_cer

FIXTURES = Path(__file__).resolve().parent / "fixtures"
REFERENCE_NAMES = ["zh", "en", "mixed"]
PNGS = sorted(FIXTURES.glob("*.png"))


def _read(path: Path) -> bytes:
    if not path.is_file():
        pytest.fail(f"missing test fixture {path}; regenerate with tests/fixtures/make_fixtures.ps1")
    return path.read_bytes()


@pytest.mark.parametrize("name", REFERENCE_NAMES)
def test_reference_texts_are_utf8_lf_no_bom(name):
    raw = _read(FIXTURES / f"{name}.txt")
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert b"\r" not in raw
    text = raw.decode("utf-8")  # strict: raises on invalid UTF-8
    assert normalize_for_cer(text) != ""


@pytest.mark.parametrize("name", REFERENCE_NAMES)
def test_every_reference_has_its_image(name):
    assert (FIXTURES / f"{name}.png").is_file()


def test_at_least_the_known_pngs_exist():
    names = {p.stem for p in PNGS}
    assert {"zh", "en", "mixed", "blank", "lowconf"} <= names


@pytest.mark.parametrize("path", PNGS, ids=lambda p: p.name)
def test_fixture_pngs_are_8bit_rgb_no_alpha(path):
    data = _read(path)
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert data[12:16] == b"IHDR"
    bit_depth, color_type = data[24], data[25]
    assert (bit_depth, color_type) == (8, 2)
