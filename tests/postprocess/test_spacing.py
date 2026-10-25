"""F2 WI-4: snapocr.postprocess.spacing.add_cjk_latin_spacing (unit lane).

Law: idempotent; only spaces are inserted, exactly one per directly adjacent
"Han | ASCII letter/digit" pair whose two characters are not both inside the
same protected span; afterwards no such pair remains; protected span contents
are unchanged. Matrix: tests-20261025-183000.md, section WI-4 (+ rev 1 L10).
"""

import pytest
from hypothesis import given

from snapocr.postprocess.chars import is_cjk, is_latin_alnum
from snapocr.postprocess.spacing import add_cjk_latin_spacing
from snapocr.postprocess.spans import protected_spans
from support.pp_strategies import mixed_text


def _is_mixed_pair(a: str, b: str) -> bool:
    return (is_cjk(a) and is_latin_alnum(b)) or (is_latin_alnum(a) and is_cjk(b))


def _same_span(spans, i: int) -> bool:
    """True when characters i and i+1 both lie inside one protected span."""
    return any(s <= i and i + 1 < e for s, e in spans)


def pairs(s: str) -> int:
    """Test-side count of adjacent Han | Latin-alnum pairs not both in one span."""
    spans = protected_spans(s)
    return sum(1 for i in range(len(s) - 1) if _is_mixed_pair(s[i], s[i + 1]) and not _same_span(spans, i))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("使用Python3", "使用 Python3"),
        ("Python3截图", "Python3 截图"),
        ("共3个", "共 3 个"),
        ("使用 Python3", "使用 Python3"),
        ("识别，Python", "识别，Python"),
        ("访问https://zh.wikipedia.org/wiki/中文", "访问 https://zh.wikipedia.org/wiki/中文"),
        ("", ""),
    ],
)
def test_examples(text, expected):
    assert add_cjk_latin_spacing(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("中a", "中 a"),
        ("a中", "a 中"),
        ("中文\nabc", "中文\nabc"),
        ("abc\n中文", "abc\n中文"),
        ("中", "中"),
        ("a", "a"),
        ("用`ls`命令", "用`ls`命令"),
        ("中\u3000a", "中\u3000a"),
        ("在D:\\资料\\a下", "在 D:\\资料\\a下"),
        # rev 1 L10: extension A ideograph
        ("\u3400a", "\u3400 a"),
    ],
)
def test_boundaries(text, expected):
    assert add_cjk_latin_spacing(text) == expected


@pytest.mark.parametrize("bad", [None, b"x"])
def test_guard_non_str(bad):
    with pytest.raises(TypeError):
        add_cjk_latin_spacing(bad)


@given(mixed_text(40))
def test_idempotent(s):
    once = add_cjk_latin_spacing(s)
    assert add_cjk_latin_spacing(once) == once


@given(mixed_text(40))
def test_inserts_exactly_one_space_per_adjacent_pair(s):
    out = add_cjk_latin_spacing(s)
    assert out.replace(" ", "") == s.replace(" ", "")
    assert out.count(" ") - s.count(" ") == pairs(s)
    assert out.count("\n") == s.count("\n")


@given(mixed_text(40))
def test_no_adjacency_and_spans_preserved(s):
    out = add_cjk_latin_spacing(s)
    assert pairs(out) == 0
    assert [out[a:b] for a, b in protected_spans(out)] == [s[a:b] for a, b in protected_spans(s)]
