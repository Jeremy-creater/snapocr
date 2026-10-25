"""F2 WI-5: snapocr.postprocess.punctuation.to_fullwidth_punctuation (unit lane).

Law: idempotent; after folding full-width marks back to ASCII the non-whitespace
characters are conserved; text without Han characters is returned unchanged;
protected span contents are unchanged; a mark run between Han characters is
always converted and a mark between digits never is.
Matrix: tests-20261025-183000.md, section WI-5 (+ rev 1 H1, H2, L6, L7, L10).
"""

from string import digits

import pytest
from hypothesis import given
from hypothesis import strategies as st

from snapocr.postprocess.chars import is_cjk
from snapocr.postprocess.punctuation import to_fullwidth_punctuation
from snapocr.postprocess.spans import protected_spans
from support.pp_strategies import SPAN_FRAGMENTS, ascii_punct, cjk, fw_punct, latin, mixed_text, span_fragments

FULLWIDTH = {",": "，", ";": "；", ":": "：", "?": "？", "!": "！", ".": "。"}
_FOLD = str.maketrans({v: k for k, v in FULLWIDTH.items()})


def fold(s: str) -> str:
    return s.translate(_FOLD)


def nonws(s: str) -> str:
    return "".join(c for c in s if not c.isspace())


# Matrix test_idempotent: mixed_text(40) with ascii_punct weighted double plus
# " , " and "..." (a tab is added as a second skippable space character).
punct_text = st.lists(
    st.one_of(
        cjk,
        cjk,
        latin,
        latin,
        st.just(" "),
        st.just("\t"),
        st.just("\n"),
        fw_punct,
        ascii_punct,
        ascii_punct,
        st.just(" , "),
        st.just("..."),
        span_fragments,
    ),
    max_size=40,
).map("".join)

_hanless_fragments = st.sampled_from([f for f in SPAN_FRAGMENTS if not any(is_cjk(c) for c in f)])
no_cjk_text = st.lists(
    st.one_of(latin, latin, st.just(" "), st.just("\t"), st.just("\n"), fw_punct, ascii_punct, ascii_punct, _hanless_fragments),
    max_size=40,
).map("".join)

han_run = st.lists(cjk, min_size=1, max_size=4).map("".join)
latin_run = st.lists(latin, min_size=1, max_size=4).map("".join)
digit_run = st.text(alphabet=digits, min_size=1, max_size=3)
spaces = st.integers(0, 2).map(lambda n: " " * n)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("识别,自动", "识别，自动"),
        ("Hello, 世界", "Hello，世界"),
        ("Hello World, snapocr 123 test.", "Hello World, snapocr 123 test."),
        ("版本 0.1，端口 11434，日期 2026-10-25。", "版本 0.1，端口 11434，日期 2026-10-25。"),
        ("什么?!", "什么？！"),
        ("什么 ?!", "什么？！"),
        ("访问 https://a.org/x,y 中文", "访问 https://a.org/x,y 中文"),
        ("见文件.txt", "见文件.txt"),
    ],
)
def test_examples(text, expected):
    assert to_fullwidth_punctuation(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("中文,English", "中文，English"),
        ("时间:10点", "时间：10点"),
        ("文件.txt", "文件.txt"),
    ],
)
def test_comma_before_latin_converts(text, expected):
    assert to_fullwidth_punctuation(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (",中文", "，中文"),
        ("中文,", "中文，"),
        ("中文!", "中文！"),
        ("约3.14倍", "约3.14倍"),
        ("共1,000个", "共1,000个"),
        ("比例1:2", "比例1:2"),
        ("好...", "好..."),
        ("好..", "好.."),
        ("好.", "好。"),
        ("中文\n,abc", "中文\n,abc"),
        ("abc,\n中文", "abc,\n中文"),
        ("中文\n, 中", "中文\n，中"),
        ("", ""),
        # rev 1 L6: all spaces / tabs on both sides of a converted run go
        ("中文  ,中", "中文，中"),
        ("中\t,a", "中，a"),
        # rev 1 L7: the "." exception is direction-specific; digit guard for all marks
        ("Python.中文", "Python。中文"),
        ("共1;2个", "共1;2个"),
        ("比例1?2", "比例1?2"),
        # rev 1 L10: extension A ideograph
        ("㐀,㐀", "㐀，㐀"),
    ],
)
def test_boundaries(text, expected):
    assert to_fullwidth_punctuation(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1. 支持翻译", "1. 支持翻译"),
        ("中文\n2. 一键翻译", "中文\n2. 一键翻译"),
        ("  3) 项目", "  3) 项目"),
        ("1.5倍", "1.5倍"),
        ("共1. 项", "共1。项"),
    ],
)
def test_list_marker_not_converted(text, expected):
    """rev 1 H1: a line-start list number keeps its ASCII mark (PRD F2-2)."""
    assert to_fullwidth_punctuation(text) == expected


@pytest.mark.parametrize(
    "text",
    ["中文 Hello, world", "安装后运行 make test."],
)
def test_english_sentence_in_chinese_line_unchanged(text):
    """rev 1 H2: context is the nearest non-space character, not the whole line."""
    assert to_fullwidth_punctuation(text) == text


@pytest.mark.parametrize("bad", [None, 1])
def test_guard_non_str(bad):
    with pytest.raises(TypeError):
        to_fullwidth_punctuation(bad)


@given(punct_text)
def test_idempotent(s):
    once = to_fullwidth_punctuation(s)
    assert to_fullwidth_punctuation(once) == once


@given(punct_text)
def test_fold_conservation(s):
    out = to_fullwidth_punctuation(s)
    assert fold(nonws(out)) == fold(nonws(s))
    assert out.count("\n") == s.count("\n")
    assert len(out) <= len(s)


@given(no_cjk_text, mixed_text(40))
def test_no_cjk_unchanged_and_spans_preserved(plain, s):
    assert to_fullwidth_punctuation(plain) == plain
    out = to_fullwidth_punctuation(s)
    assert [out[a:b] for a, b in protected_spans(out)] == [s[a:b] for a, b in protected_spans(s)]


@given(
    han_run,
    spaces,
    st.sampled_from([",", ";", ":", "?", "!", "."]),
    spaces,
    han_run,
    digit_run,
    st.sampled_from([",", ".", ":"]),
    digit_run,
    latin_run,
    st.sampled_from([",", ";", ":", "?", "!", "."]),
    st.booleans(),
    st.sampled_from(["", " ", "\t", "  "]),
    digit_run,
)
def test_conversion_completeness_and_digit_guard(
    h1, sp1, mark, sp2, h2, d1, num_mark, d2, lat, en_mark, prefixed, indent, list_no
):
    # (a) Han · mark · spaces · Han: converted, no space on either side
    assert to_fullwidth_punctuation(h1 + sp1 + mark + sp2 + h2) == h1 + FULLWIDTH[mark] + h2
    # (b) Han · digits · mark · digits · Han: the mark stays
    numeric = h1 + d1 + num_mark + d2 + h2
    assert to_fullwidth_punctuation(numeric) == numeric
    # (c) rev 1 H2: Han · " " · latin · mark · spaces · latin: unchanged
    english = h1 + " " + lat + en_mark + sp2 + lat
    assert to_fullwidth_punctuation(english) == english
    # (d) rev 1 H1: (line start) digits{1,3} · "." · " " · Han: unchanged
    listed = (h1 + "\n" if prefixed else "") + indent + list_no + ". " + h2
    assert to_fullwidth_punctuation(listed) == listed
