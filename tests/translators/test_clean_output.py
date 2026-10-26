"""F4 WI-5: <think> block removal (F4-3, matrix Q11)."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from snapocr.translators.protocol import clean_output
from support.tr_strategies import tag_soup

TAGS = ("<think>", "</think>")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("<think>x</think>\n  Hello  ", "Hello"),
        ("a</think>b", "b"),
        ("Hi<think>unfinished", "Hi"),
        ("<think>only</think>", ""),
        ("<think>\n\n</think>\n\nThe weather", "The weather"),
        ("A<think>1</think>B<think>2</think>C", "ABC"),
        ("<think>a</think>x</think>y", "y"),
        ("<THINK>x</THINK>Hi", "<THINK>x</THINK>Hi"),
        ("  plain  ", "plain"),
        ("", ""),
    ],
    ids=repr,
)
def test_clean_examples(raw, expected):
    assert clean_output(raw) == expected


def test_clean_tags_formed_by_removal():
    assert clean_output("<thi<think>x</think>nk>Hi") == ""
    assert clean_output("ok </th<think>x</think>ink> yes") == "yes"


@given(tag_soup())
def test_clean_idempotent(s):
    once = clean_output(s)
    assert clean_output(once) == once


def _is_subsequence(small: str, big: str) -> bool:
    it = iter(big)
    return all(c in it for c in small)


@given(tag_soup())
def test_clean_tag_free_and_subsequence(s):
    out = clean_output(s)
    assert not any(tag in out for tag in TAGS)
    assert _is_subsequence(out, s)
    assert out == out.strip()


@given(st.text().filter(lambda s: not any(tag in s for tag in TAGS)))
def test_clean_identity_on_tag_free(s):
    assert clean_output(s) == s.strip()


no_angle = st.text().filter(lambda s: "<" not in s and ">" not in s)


@given(no_angle, no_angle, no_angle)
def test_clean_structured_oracles(a, b, c):
    assert clean_output("<think>" + a + "</think>" + b) == b.strip()
    assert clean_output(a + "</think>" + b) == b.strip()
    assert clean_output(b + "<think>" + a) == b.strip()
    assert clean_output(c + "<think>" + a + "</think>" + b) == (c + b).strip()
