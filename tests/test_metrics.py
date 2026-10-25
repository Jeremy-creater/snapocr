"""WI-8: snapocr.metrics -- edit_distance, cer, normalize_for_cer (unit lane)."""

import pytest
from hypothesis import example, given
from hypothesis import strategies as st

from snapocr.metrics import cer, edit_distance, normalize_for_cer

# ASCII, CJK, fullwidth punctuation, combining marks, and an astral-plane CJK char.
_ALPHABET = st.one_of(
    st.characters(min_codepoint=0x20, max_codepoint=0x7E),
    st.characters(min_codepoint=0x4E00, max_codepoint=0x4E2F),
    st.sampled_from(list("，。！？：；（）、「」")),
    st.sampled_from(["́", "̈", "̣"]),
    st.just("𠮷"),
)
_WHITESPACE = st.sampled_from([" ", "\t", "\n", "\r", "　", " ", " ", "\x0b", "\x0c"])


def texts(max_size: int) -> st.SearchStrategy[str]:
    return st.text(alphabet=_ALPHABET, max_size=max_size)


def _reference_normalize(s: str) -> str:
    return "".join(c for c in s if not c.isspace())


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("kitten", "sitting", 3),
        ("flaw", "lawn", 2),
        ("ab", "ba", 2),
        ("汉字", "汉子", 1),
        ("𠮷", "吉", 1),
    ],
)
def test_known_examples(a: str, b: str, expected: int) -> None:
    assert edit_distance(a, b) == expected


def test_known_example_cer() -> None:
    assert cer("使用Pyth0n", "使用Python") == 1 / 8


@pytest.mark.parametrize(
    ("hyp", "ref", "expected_distance"),
    [
        ("，", ",", 1),
        ("é", "é", 2),
    ],
)
def test_cer_does_not_normalize(hyp: str, ref: str, expected_distance: int) -> None:
    assert edit_distance(hyp, ref) == expected_distance


def test_cer_does_not_strip_whitespace() -> None:
    assert cer("a b", "ab") == 0.5


def test_cer_empty_and_disjoint_boundaries() -> None:
    both_empty = cer("", "")
    assert both_empty == 0.0
    assert type(both_empty) is float

    with pytest.raises(ValueError, match="ref"):
        cer("x", "")

    for hyp, ref, expected in [("", "abc", 1.0), ("xyz", "abc", 1.0), ("abcd", "a", 3.0)]:
        result = cer(hyp, ref)
        assert result == expected
        assert type(result) is float


@given(texts(30), texts(30))
def test_identity_and_nonnegativity(a: str, b: str) -> None:
    if a:
        assert cer(a, a) == 0
    d = edit_distance(a, b)
    assert d >= 0
    assert (d == 0) == (a == b)


@given(texts(20), texts(20), texts(20))
@example("ca", "ac", "abc")
def test_symmetry_and_triangle(a: str, b: str, c: str) -> None:
    assert edit_distance(a, b) == edit_distance(b, a)
    assert edit_distance(a, c) <= edit_distance(a, b) + edit_distance(b, c)


@given(texts(30), texts(30))
def test_length_bounds(a: str, b: str) -> None:
    d = edit_distance(a, b)
    assert abs(len(a) - len(b)) <= d <= max(len(a), len(b))


@given(texts(20), texts(20))
def test_append_costs_exactly_its_length(a: str, s: str) -> None:
    assert edit_distance(a, a + s) == len(s)
    assert edit_distance(s + a, a) == len(s)


@given(texts(30), texts(30).filter(bool))
def test_cer_equals_distance_over_ref_len(hyp: str, ref: str) -> None:
    assert cer(hyp, ref) == edit_distance(hyp, ref) / len(ref)


@given(st.text(alphabet=st.one_of(_ALPHABET, _WHITESPACE), max_size=40))
@example("使用 Python　截图\n\t识别 ")
@example("a​b")
def test_normalize_matches_model_and_is_idempotent(s: str) -> None:
    n = normalize_for_cer(s)
    assert n == _reference_normalize(s)
    assert normalize_for_cer(n) == n


@pytest.mark.parametrize(
    ("s", "expected"),
    [
        ("使用 Python　截图\n\t识别 ", "使用Python截图识别"),
        ("a​b", "a​b"),
    ],
)
def test_normalize_fixed_examples(s: str, expected: str) -> None:
    assert normalize_for_cer(s) == expected
