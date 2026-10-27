"""M4 WI-16: table OCR on real table screenshots (PRD F16-4; engine lane).

The samples and the conventions of their expected grids are described in
``tests/fixtures/table/README.md``. Every sample must have the expected
number of rows and columns; cells are compared without whitespace, at least
95% per sample and 98% over all samples (the two known misses are
recognition errors, out of F16's scope).

Missing fixtures or models FAIL; nothing skips.
"""

import re
from pathlib import Path

import pytest

from snapocr.postprocess.table import table_cells

pytestmark = pytest.mark.engine

TABLES = Path(__file__).resolve().parent.parent / "fixtures" / "table"
NAMES = ["schedule", "groceries", "products", "quarterly", "grades", "merged", "sales"]
MIN_PER_SAMPLE = 0.95
MIN_OVERALL = 0.98


def _read(path: Path) -> bytes:
    if not path.is_file():
        pytest.fail(f"missing test fixture {path}; see tests/fixtures/table/README.md")
    return path.read_bytes()


def expected_grid(name: str) -> list[list[str]]:
    text = _read(TABLES / f"{name}.expected.tsv").decode("utf-8")
    return [line.split("\t") for line in text.split("\n") if line]


def _bare(text: str) -> str:
    return re.sub(r"\s+", "", text)


@pytest.fixture(scope="module")
def recognized(loaded_engine):
    return {name: table_cells(loaded_engine.recognize(_read(TABLES / f"{name}.png"))) for name in NAMES}


def _matches(got: list[list[str]], want: list[list[str]]) -> int:
    return sum(_bare(a) == _bare(b) for g, w in zip(got, want) for a, b in zip(g, w))


@pytest.mark.parametrize("name", NAMES)
def test_rows_columns_and_cells(recognized, name):
    got, want = recognized[name], expected_grid(name)
    assert [len(row) for row in got] == [len(row) for row in want], got
    assert _matches(got, want) >= MIN_PER_SAMPLE * sum(map(len, want)), got


def test_cells_over_all_samples(recognized):
    total = sum(sum(map(len, expected_grid(name))) for name in NAMES)
    right = sum(_matches(recognized[name], expected_grid(name)) for name in NAMES)
    assert right >= MIN_OVERALL * total, f"{right} of {total}"
