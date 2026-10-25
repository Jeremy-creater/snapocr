"""WI-9 (PRD F1-7): recognition accuracy on the committed samples (engine lane).

Comparison: block texts concatenated in returned order, then normalize_for_cer
on both sides (inside assert_cer_within). Limit: CER <= 0.02 per image.
No law: these are oracle checks on a few samples; the mutation test below is
the S6 relation proving the gate can fail.
"""

import math
from pathlib import Path

import pytest

from snapocr.metrics import edit_distance, normalize_for_cer
from support.cer_check import assert_cer_within

pytestmark = pytest.mark.engine

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
NAMES = ["zh", "en", "mixed"]
CER_LIMIT = 0.02
FOREIGN = "□"


def _read(path: Path) -> bytes:
    if not path.is_file():
        pytest.fail(f"missing test fixture {path}; regenerate with tests/fixtures/make_fixtures.ps1")
    return path.read_bytes()


@pytest.fixture(scope="module")
def recognized(loaded_engine):
    cache: dict[str, str] = {}

    def get(name: str) -> str:
        if name not in cache:
            result = loaded_engine.recognize(_read(FIXTURES / f"{name}.png"))
            cache[name] = "".join(block.text for block in result.blocks)
        return cache[name]

    return get


def _reference(name: str) -> str:
    return _read(FIXTURES / f"{name}.txt").decode("utf-8")


@pytest.mark.parametrize("name", NAMES)
def test_fixture_cer_within_limit(recognized, name):
    measured = assert_cer_within(recognized(name), _reference(name), CER_LIMIT, name)
    print(f"[WI-9] {name}: CER={measured:.4f}")


@pytest.mark.parametrize("name", NAMES)
def test_cer_gate_rejects_mutated_reference(recognized, name):
    hyp = normalize_for_cer(recognized(name))
    ref = normalize_for_cer(_reference(name))
    assert FOREIGN not in ref
    length = len(ref)
    d0 = edit_distance(hyp, ref)
    k = math.floor(CER_LIMIT * length) + 1 + d0
    if k > length:
        pytest.fail(f"{name}: baseline distance {d0} too large to build a mutation (L={length})")
    positions = [i * length // k for i in range(k)]
    assert len(set(positions)) == k
    chars = list(ref)
    for p in positions:
        chars[p] = FOREIGN
    mutated = "".join(chars)
    # d(hyp, mutated) >= d(ref, mutated) - d0 = k - d0 > CER_LIMIT * L
    with pytest.raises(AssertionError):
        assert_cer_within(hyp, mutated, CER_LIMIT, f"{name}-mutated")
