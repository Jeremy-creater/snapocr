"""F2 WI-3: snapocr.postprocess.paragraphs (unit lane).

merge_paragraphs law: idempotent under a fixed region (S5, Q1); non-whitespace
characters are conserved in order (S4); no merge across a paragraph gap and
the gap count is unchanged (S4); the line grouping equals the label oracle
(S4); monotone in ``full_ratio`` (S6); invariant under a horizontal
translation of lines and region together (S6, rev 1 H3).

lines_to_text law: structural round trip -- dropping the empty lines gives the
line texts, and an empty line precedes exactly the lines at index > 0 with
``gap_before`` (S5, Q10).

Decisions applied: Q1 (explicit region), Q7 (sentence-end closers, list
items), Q10 (empty lines), Q11 (seam rule) plus the ASCII-letter hyphen rule,
Q16 (guards). Fullness is ``right - region_left >= full_ratio * (region_right
- region_left)`` (H3). Expected values come from labels in
``support.pp_strategies``, never from production code.
"""

import math
import re

import pytest
from hypothesis import given
from hypothesis import strategies as st

from snapocr.postprocess.layout import Line
from snapocr.postprocess.paragraphs import lines_to_text, merge_paragraphs
from support.pp_strategies import block_text, free_right_lines, labeled_paragraph_lines

W = 512.0
FULL = W
SHORT = 0.5 * W


def ln(text, right=FULL, *, left=0.0, i=0, gap=False):
    """A line at row ``i`` (top 20*i, height 16)."""
    return Line(text, left, right, 20.0 * i, 20.0 * i + 16, gap)


def pair(first, second, *, first_right=FULL, second_right=FULL, gap=False):
    return [ln(first, first_right, i=0), ln(second, second_right, i=1, gap=gap)]


def nonws(s):
    return re.sub(r"\s", "", s)


def texts(lines):
    return [line.text for line in lines]


# --------------------------------------------------------------------------
# merge_paragraphs: examples and boundaries
# --------------------------------------------------------------------------


def test_three_full_lines_merge():
    lines = [
        Line("截图识别工具在后台常驻，按下快捷键后", 0.0, FULL, 0.0, 16.0, True),
        Line("选择区域，识别结果会自动复制到剪", 0.0, FULL, 20.0, 36.0, False),
        Line("贴板中。", 0.0, 200.0, 40.0, 56.0, False),
    ]
    out = merge_paragraphs(lines, region=(0.0, W))
    assert out == (
        Line(
            "截图识别工具在后台常驻，按下快捷键后选择区域，识别结果会自动复制到剪贴板中。",
            0.0,
            200.0,
            0.0,
            56.0,
            True,
        ),
    )


@pytest.mark.parametrize(
    ("lines", "n_out"),
    [
        pytest.param(pair("第一章 概述", "正文从这里开始", first_right=0.3 * W), 2, id="a-short-title"),
        pytest.param(pair("正文的第一行没有标点", "第二行", gap=True), 2, id="b-gap"),
        pytest.param(pair("正文的第一行没有标点", "1. 列表项"), 2, id="c-list-item"),
        pytest.param(pair("正文的第一行到此结束。", "第二行"), 2, id="d-sentence-end"),
        pytest.param(pair("正文的第一行没有标点", "第二行"), 1, id="e-all-hold"),
    ],
)
def test_each_condition_blocks_merge(lines, n_out):
    out = merge_paragraphs(lines, region=(0.0, W))
    assert len(out) == n_out
    if n_out == 2:
        assert out == tuple(lines)
    else:
        assert out == (Line("正文的第一行没有标点第二行", 0.0, FULL, 0.0, 36.0, False),)


@pytest.mark.parametrize(
    ("first", "second", "joined"),
    [
        ("text is recognized and", "copied to the clipboard", "text is recognized and copied to the clipboard"),
        ("recog-", "nized", "recog-nized"),
        ("2026-", "10", "2026- 10"),
        ("区域，", "Hello", "区域，Hello"),
    ],
)
def test_seams_english_and_hyphen(first, second, joined):
    out = merge_paragraphs(pair(first, second), region=(0.0, W))
    assert texts(out) == [joined]


def test_boundaries_empty_and_single():
    assert merge_paragraphs(()) == ()
    assert merge_paragraphs([]) == ()
    one = (ln("只有一行", SHORT),)
    assert merge_paragraphs(one) == one
    assert merge_paragraphs(one, region=(0.0, W)) == one


def test_boundary_full_ratio_exact():
    ratio = 0.85
    at = merge_paragraphs(pair("满行比例正好临界", "下一行", first_right=ratio * W), full_ratio=ratio, region=(0.0, W))
    assert texts(at) == ["满行比例正好临界下一行"]
    below = pair("满行比例差一点", "下一行", first_right=ratio * W - 0.25)
    assert merge_paragraphs(below, full_ratio=ratio, region=(0.0, W)) == tuple(below)


@pytest.mark.parametrize(
    "first",
    [
        "他说：「好。」",
        'He said "ok."',
        "他说：「好。」）",  # L2: several closers
        "到此为止…",
        "问题？”",
        "对吧?'",
    ],
)
def test_sentence_end_with_closers_blocks_merge(first):
    lines = pair(first, "下一行")
    assert merge_paragraphs(lines, region=(0.0, W)) == tuple(lines)


def test_closing_chars_alone_are_not_sentence_end():
    # M4: the char before the closers is not sentence-end punctuation.
    out = merge_paragraphs(pair("……请参见《使用手册》", "第三节"), region=(0.0, W))
    assert texts(out) == ["……请参见《使用手册》第三节"]
    out = merge_paragraphs(pair("他说的「好」", "是指这个"), region=(0.0, W))
    assert texts(out) == ["他说的「好」是指这个"]


def test_all_list_items_full_lines_do_not_merge():
    lines = [ln("1. 第一项内容", i=0), ln("2. 第二项内容", i=1), ln("3. 第三项内容", i=2)]
    assert merge_paragraphs(lines, region=(0.0, W)) == tuple(lines)


@pytest.mark.parametrize(
    "second",
    [
        "- 项",
        "* 项",
        "•项",
        "·项",  # L1
        "1. 项",
        "12. 项",  # L1
        "1.项",  # L1
        "1) 项",
        "1、项",
        "(1)项",
        "（1）项",
        "①项",
        "⑳项",
        "一、项",
        "十二、项",  # L1
    ],
)
def test_list_item_next_line_blocks_merge(second):
    lines = pair("正文没有结束的满行", second)
    assert merge_paragraphs(lines, region=(0.0, W)) == tuple(lines)


@pytest.mark.parametrize(
    ("second", "joined"),
    [
        ("1.5倍速度", "正文没有结束的满行1.5倍速度"),
        ("-5度", "正文没有结束的满行-5度"),
        ("1000. 项", "正文没有结束的满行1000. 项"),  # L1: four digits is not a list number
    ],
)
def test_not_list_items_merge(second, joined):
    out = merge_paragraphs(pair("正文没有结束的满行", second), region=(0.0, W))
    assert texts(out) == [joined]


def test_region_left_is_respected():
    # H3 S2 examples, W = 512.
    shifted = [ln("区域右移后不满的行", 1024.0 + 384.0, left=1024.0, i=0), ln("第二行", 1536.0, left=1024.0, i=1)]
    assert merge_paragraphs(shifted, region=(1024.0, 1536.0)) == tuple(shifted)
    indented = [ln("缩进但满行的第一行", 512.0, left=128.0, i=0), ln("第二行", 512.0, i=1)]
    out = merge_paragraphs(indented, region=(0.0, 512.0))
    assert out == (Line("缩进但满行的第一行第二行", 128.0, 512.0, 0.0, 36.0, False),)


def test_region_none_uses_min_left_max_right():
    # L3: R = 612; first right 528 is full for (0, 612) but not for (100, 612).
    lines = [ln("左边距一百的第一行", 528.0, left=100.0, i=0), ln("第二行", 612.0, left=100.0, i=1)]
    assert len(merge_paragraphs(lines, region=(0.0, 612.0))) == 1  # precondition: regions disagree
    expected = merge_paragraphs(lines, region=(100.0, 612.0))
    assert len(expected) == 2
    assert merge_paragraphs(lines) == expected


@pytest.mark.parametrize("ratio", [0, -0.1, 1.01, math.nan, math.inf, -math.inf])
def test_guards(ratio):
    with pytest.raises(ValueError, match="full_ratio"):
        merge_paragraphs(pair("甲", "乙"), full_ratio=ratio)


@pytest.mark.parametrize("ratio", ["0.85", None, True])
def test_full_ratio_type_guard(ratio):
    with pytest.raises(TypeError, match="full_ratio"):
        merge_paragraphs(pair("甲", "乙"), full_ratio=ratio)


@pytest.mark.parametrize("bad", [None, "text", 42, ["text"], (ln("甲"), "乙")])
def test_lines_type_guard(bad):
    with pytest.raises(TypeError):
        merge_paragraphs(bad)
    with pytest.raises(TypeError):
        lines_to_text(bad)


def test_full_ratio_one_is_allowed():
    out = merge_paragraphs(pair("恰好满行", "下一行"), full_ratio=1, region=(0.0, W))
    assert texts(out) == ["恰好满行下一行"]


# --------------------------------------------------------------------------
# merge_paragraphs: properties
# --------------------------------------------------------------------------


@given(labeled_paragraph_lines())
def test_matches_labeled_oracle(case):
    lines, expected = case
    assert merge_paragraphs(lines, full_ratio=0.85, region=(0.0, W)) == expected


def _region(lines):
    return (min(line.left for line in lines), max(line.right for line in lines))


@given(free_right_lines())
def test_idempotent_with_fixed_region(lines):
    region = _region(lines)
    once = merge_paragraphs(lines, region=region)
    assert merge_paragraphs(once, region=region) == once


@given(free_right_lines())
def test_conservation_order_and_gap_count(lines):
    out = merge_paragraphs(lines, region=_region(lines))
    assert "".join(nonws(line.text) for line in out) == "".join(nonws(line.text) for line in lines)
    assert len(out) <= len(lines)
    assert sum(line.gap_before for line in out) == sum(line.gap_before for line in lines)
    for line in lines:
        if line.gap_before:
            assert any(nonws(o.text).startswith(nonws(line.text)) for o in out)


_RATIOS = [0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 1.0]


@given(free_right_lines(), st.lists(st.sampled_from(_RATIOS), min_size=2, max_size=2).map(sorted))
def test_full_ratio_monotone_coarsening(lines, ratios):
    r1, r2 = ratios
    coarse = merge_paragraphs(lines, full_ratio=r1)
    fine = merge_paragraphs(lines, full_ratio=r2)
    assert len(coarse) <= len(fine)
    j = 0
    for c in coarse:
        acc = ""
        while len(acc) < len(nonws(c.text)):
            acc += nonws(fine[j].text)
            j += 1
        assert acc == nonws(c.text)
    assert j == len(fine)


def _shift(lines, dx):
    return tuple(Line(x.text, x.left + dx, x.right + dx, x.top, x.bottom, x.gap_before) for x in lines)


# 0.875 * 512 = 448 is exact, so the critical right stays critical after any
# integer shift; with 0.85 the shifted sum dx + 0.85*512 is rounded and the
# critical case could flip on float error rather than on the rule.
@given(labeled_paragraph_lines(ratio=0.875), st.integers(1, 2048))
def test_region_translation_invariance(case, dx):
    lines, expected = case
    shifted = _shift(lines, dx)
    base = merge_paragraphs(lines, full_ratio=0.875, region=(0.0, W))
    moved = merge_paragraphs(shifted, full_ratio=0.875, region=(dx, dx + W))
    assert [(x.text, x.gap_before) for x in moved] == [(x.text, x.gap_before) for x in base]
    assert base == expected
    auto = [(x.text, x.gap_before) for x in merge_paragraphs(lines, full_ratio=0.875)]
    auto_moved = [(x.text, x.gap_before) for x in merge_paragraphs(shifted, full_ratio=0.875)]
    assert auto_moved == auto


# --------------------------------------------------------------------------
# lines_to_text
# --------------------------------------------------------------------------


def test_lines_to_text_examples():
    a, b = ln("A"), ln("B", i=1)
    a_gap, b_gap = ln("A", gap=True), ln("B", i=1, gap=True)
    assert lines_to_text(()) == ""
    assert lines_to_text([a]) == "A"
    assert lines_to_text([a, b_gap]) == "A\n\nB"
    assert lines_to_text([a_gap, b]) == "A\nB"
    assert lines_to_text([a_gap]) == "A"


@given(st.lists(st.tuples(block_text(), st.booleans()), min_size=1, max_size=8))
def test_lines_to_text_roundtrip(rows):
    # min_size=1: for () the output is "" (example above) and "".split("\n")
    # is [""], so the empty-line count law below only holds for >= 1 line.
    lines = [ln(t, i=i, gap=g) for i, (t, g) in enumerate(rows)]
    out = lines_to_text(lines)
    parts = out.split("\n")
    assert [p for p in parts if p] == [t for t, _ in rows]
    assert parts.count("") == sum(g for _, g in rows[1:])
    expected_parts = []
    for i, (t, g) in enumerate(rows):
        if i > 0 and g:
            expected_parts.append("")
        expected_parts.append(t)
    assert parts == expected_parts
