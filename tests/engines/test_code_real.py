"""M3 WI-13: code OCR on real code screenshots (PRD F13-6; engine lane).

The samples and how their expected texts differ from the source files are
described in ``tests/fixtures/code/README.md``. Only layout is checked: the
line count, blank lines and the indentation of every line that is non-blank
on both sides. Character errors are out of scope (F13-5).

Missing fixtures or models FAIL; nothing skips.
"""

from pathlib import Path

import pytest

from snapocr.postprocess.code import code_text

pytestmark = pytest.mark.engine

CODE = Path(__file__).resolve().parent.parent / "fixtures" / "code"
NAMES = ["nested", "continuation", "proportional"]
# Whole lines the engine may drop (a lone ")" or "}"); they come out blank.
MAX_LOST_LINES = 2


def _read(path: Path) -> bytes:
    if not path.is_file():
        pytest.fail(f"missing test fixture {path}; see tests/fixtures/code/README.md")
    return path.read_bytes()


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


@pytest.mark.parametrize("name", NAMES)
def test_lines_blank_lines_and_indentation(loaded_engine, name):
    expected = _read(CODE / f"{name}.expected.txt").decode("utf-8").splitlines()
    out = code_text(loaded_engine.recognize(_read(CODE / f"{name}.png"))).split("\n")
    assert len(out) == len(expected), "\n".join(out)
    both = 0
    for i, (got, want) in enumerate(zip(out, expected), 1):
        if not want.strip():
            assert not got.strip(), f"line {i} should be blank: {got!r}"
        elif got.strip():
            both += 1
            assert _indent(got) == _indent(want), f"line {i}: {got!r} vs {want!r}"
    assert both >= sum(1 for line in expected if line.strip()) - MAX_LOST_LINES
