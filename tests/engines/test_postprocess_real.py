"""F2 WI-8: real OCR followed by post-processing (engine lane).

The real RapidOCR engine recognizes the committed samples, then the default
``postprocess`` turns the result into text. These are oracle checks on a few
synthetic samples (no law of their own); the one relation is PRD §9
"post-processing never makes CER worse" (S6), comparing the output with the
raw block texts joined in engine order. This is also the real path for the
synthetic-coordinate layout / paragraph tests of WI-2 and WI-3.

Missing fixtures or models FAIL (``_read`` / ``loaded_engine``); nothing skips.
"""

from pathlib import Path

import pytest

from snapocr.metrics import cer, normalize_for_cer
from snapocr.postprocess import postprocess
from support.cer_check import assert_cer_within

pytestmark = pytest.mark.engine

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
CER_LIMIT = 0.02
# Full chain output for mixed.png (same literal as test_pipeline.F1_EXPECTED).
MIXED_EXPECTED = "使用 Python3 截图识别，自动复制到剪贴板。\nHello World, snapocr 123 test."


def _read(path: Path) -> bytes:
    if not path.is_file():
        pytest.fail(f"missing test fixture {path}; regenerate with tests/fixtures/make_fixtures.ps1")
    return path.read_bytes()


def _text(name: str) -> str:
    return _read(FIXTURES / name).decode("utf-8")


@pytest.fixture(scope="module")
def recognized(loaded_engine):
    """name -> OcrResult of ``{name}.png``, recognized once per module."""
    cache = {}

    def get(name: str):
        if name not in cache:
            cache[name] = loaded_engine.recognize(_read(FIXTURES / f"{name}.png"))
        return cache[name]

    return get


@pytest.mark.parametrize("name", ["zh", "en", "mixed"])
def test_line_structure_and_cer(recognized, name):
    ref_lines = [line for line in _text(f"{name}.txt").splitlines() if line.strip()]
    out_lines = postprocess(recognized(name)).split("\n")
    assert len(out_lines) == len(ref_lines), out_lines
    assert "" not in out_lines
    for i, (out, ref) in enumerate(zip(out_lines, ref_lines)):
        assert_cer_within(out, ref, CER_LIMIT, f"{name} line {i + 1}")


def test_mixed_exact(recognized):
    assert postprocess(recognized("mixed")) == MIXED_EXPECTED


def test_wrap_paragraph_structure(recognized):
    expected = _text("wrap.expected.txt").splitlines()
    out_lines = postprocess(recognized("wrap")).split("\n")
    assert len(out_lines) == len(expected), out_lines
    assert [line == "" for line in out_lines] == [line == "" for line in expected]
    for i, (out, ref) in enumerate(zip(out_lines, expected)):
        if ref:
            assert_cer_within(out, ref, CER_LIMIT, f"wrap line {i + 1}")


@pytest.mark.parametrize("name", ["zh", "en", "mixed", "wrap"])
def test_postprocess_never_worsens_cer(recognized, name):
    result = recognized(name)
    ref = normalize_for_cer(_text(f"{name}.txt"))
    raw = normalize_for_cer("".join(block.text for block in result.blocks))
    post = normalize_for_cer(postprocess(result))
    assert ref
    assert cer(post, ref) <= cer(raw, ref), (post, raw)
