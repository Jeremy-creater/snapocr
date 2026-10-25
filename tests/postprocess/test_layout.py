"""F2 WI-2: snapocr.postprocess.layout.build_lines (unit lane).

Law: the result does not depend on block order (S4); the multiset of
non-whitespace characters is conserved (S4); a global translation or a
power-of-two scaling leaves the lines unchanged up to the same transform (S6);
a clean row grid round-trips to its generated rows (S5); on realistic layouts
the reading order is monotone (S4).

Q12 restriction: reading-order monotonicity (line ``top`` non-decreasing) is
asserted ONLY on realistic layouts -- blocks of equal height with vertical
jitter <= 0.25h (``jittered_rows``). On arbitrary layouts a very tall block can
pull a line's median ``top`` above the previous line, so there we assert only
conservation, order independence and translation / scale invariance.

Decisions applied: Q2 (median line coordinates, strict gap), Q3 (line-break
chars in a block become spaces), Q4 (zero-height blocks), Q11 (seam rule),
Q16 (TypeError on non-OcrResult). Expected row texts come from the test-side
``_seam_join`` in ``support.pp_strategies``, never from production code.
"""

from collections import Counter

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from snapocr.engines.types import OcrResult, TextBlock
from snapocr.postprocess import layout
from snapocr.postprocess.layout import Line, build_lines
from support.pp_strategies import (
    arbitrary_layouts,
    grid_layouts,
    jittered_rows,
    rect,
    render_grid,
)

# Q3: every character str.splitlines treats as a line boundary.
LINE_BREAK_CHARS = ["\n", "\r", "\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85", " ", " "]


def _lines(*blocks: TextBlock) -> tuple[Line, ...]:
    return build_lines(OcrResult(blocks))


def _texts(lines) -> list[str]:
    return [line.text for line in lines]


def _nonws(s: str) -> str:
    return "".join(c for c in s if not c.isspace())


# --- examples and boundaries ------------------------------------------------


def test_f1_measured_split_line():
    hello = rect("Hello World, snapocr 123 test.", 24, 112, 470, 150)
    copy = rect("自动复制到剪贴板。", 436, 31, 720, 67)
    use = rect("使用Python3截图识别，", 24, 30, 430, 68)
    lines = _lines(hello, copy, use)
    assert _texts(lines) == ["使用Python3截图识别，自动复制到剪贴板。", "Hello World, snapocr 123 test."]
    assert lines[0] == Line("使用Python3截图识别，自动复制到剪贴板。", 24.0, 720.0, 30.5, 67.5, False)
    assert lines[1] == Line("Hello World, snapocr 123 test.", 24.0, 470.0, 112.0, 150.0, False)


def test_empty_result():
    assert build_lines(OcrResult(())) == ()
    assert _lines(rect("  \t", 0, 0, 10, 10)) == ()


def test_single_block_fields():
    block = TextBlock(" ab ", ((10, 5), (50, 7), (48, 25), (9, 22)), 0.9)
    assert _lines(block) == (Line("ab", 9.0, 50.0, 5.0, 25.0, False),)


def test_contained_block_keeps_outer_right():
    # L4: a block horizontally inside another must not shrink the line's right edge.
    lines = _lines(rect("乙", 10, 0, 40, 16), rect("甲", 0, 0, 100, 16))
    assert lines == (Line("甲乙", 0.0, 100.0, 0.0, 16.0, False),)


def test_same_row_left_order_and_seams():
    blocks = [
        rect("中文", 120, 0, 150, 16),
        rect("Hello", 0, 0, 50, 16),
        rect("，好", 160, 0, 190, 16),
        rect("World", 60, 0, 110, 16),
    ]
    assert _texts(_lines(*blocks)) == ["Hello World中文，好"]


def test_identical_coordinates_tiebreak():
    a, b = rect("a", 0, 0, 16, 16), rect("b", 0, 0, 16, 16)
    assert _texts(_lines(b, a)) == ["a b"]
    assert _lines(a, b) == _lines(b, a)
    x1 = rect("x", 0, 0, 16, 16, score=0.6)
    x2 = rect("x", 0, 0, 16, 16, score=0.9)
    assert _texts(_lines(x1, x2)) == ["x x"]
    assert _lines(x1, x2) == _lines(x2, x1)


def test_overlap_threshold_edges():
    a = rect("甲", 0, 0, 16, 16)
    y = 16 - layout.SAME_LINE_OVERLAP * 16  # overlap exactly at the threshold
    b = rect("乙", 100, y, 116, y + 16)
    assert _texts(_lines(b, a)) == ["甲乙"]
    b2 = rect("乙", 100, y + 0.25, 116, y + 16.25)
    assert _texts(_lines(b2, a)) == ["甲", "乙"]


@pytest.mark.parametrize("order", [(0, 1, 2), (2, 1, 0), (1, 2, 0)])
def test_tall_block_does_not_chain_lines(order):
    blocks = [rect("甲", 0, 0, 50, 20), rect("乙", 0, 30, 50, 50), rect("丙", 100, 0, 150, 50)]
    # T joins A; the median range becomes 0..35 and B overlaps only 5 < 0.5 * 20.
    assert _texts(_lines(*(blocks[i] for i in order))) == ["甲丙", "乙"]


def test_short_block_after_tall_block_same_line():
    # M2: the base is the shorter height (10); overlap 10 >= 0.5 * 10.
    lines = _lines(rect("乙", 100, 26, 150, 36), rect("丙", 0, 0, 50, 40))
    assert _texts(lines) == ["丙乙"]


def test_line_median_coordinates():
    # M1: top/bottom are medians, and a block is compared with the median range.
    three = [rect("甲", 0, 0, 16, 16), rect("乙", 20, 0, 36, 16), rect("丙", 40, 7, 56, 23)]
    lines = _lines(*three)
    assert _texts(lines) == ["甲乙丙"]
    assert (lines[0].top, lines[0].bottom) == (0.0, 16.0)

    lines = _lines(*three, rect("丁", 60, 9, 76, 25))  # overlap 7 < 8 with 0..16
    assert _texts(lines) == ["甲乙丙", "丁"]
    assert (lines[0].top, lines[0].bottom) == (0.0, 16.0)

    # Anchoring on the first block would split off the 9..25 block (overlap 7 with 0..16).
    four = [
        rect("一", 0, 0, 16, 16),
        rect("二", 20, 4, 36, 20),
        rect("三", 40, 4, 56, 20),
        rect("四", 60, 9, 76, 25),
    ]
    assert _texts(_lines(*four)) == ["一二三四"]
    assert _texts(_lines(*reversed(four))) == ["一二三四"]


def test_zero_height_blocks():
    row = rect("甲", 0, 0, 16, 16)
    # (a) zero-height block whose y lies inside the row's median range
    assert _texts(_lines(row, rect("乙", 100, 8, 116, 8))) == ["甲乙"]
    # (b) zero-height block below the row
    assert _texts(_lines(rect("乙", 100, 50, 116, 50), row)) == ["甲", "乙"]
    # (c) only zero-height blocks: no division by zero, median line height 0 -> no gaps
    lines = _lines(rect("甲", 0, 0, 16, 0), rect("乙", 100, 0, 116, 0), rect("丙", 0, 40, 16, 40))
    assert _texts(lines) == ["甲乙", "丙"]
    assert [line.gap_before for line in lines] == [False, False]


def test_paragraph_gap_edges():
    critical = layout.PARAGRAPH_GAP * 16
    two = _lines(rect("甲", 0, 0, 16, 16), rect("乙", 0, 16 + critical, 16, 32 + critical))
    assert [line.gap_before for line in two] == [False, False]

    y = 16 + critical + 0.25
    two = _lines(rect("甲", 0, 0, 16, 16), rect("乙", 0, y, 16, y + 16))
    assert [line.gap_before for line in two] == [False, True]

    y2 = 16 + critical
    y3 = y2 + 16 + 5 * 16
    three = _lines(
        rect("丙", 0, y3, 16, y3 + 16), rect("甲", 0, 0, 16, 16), rect("乙", 0, y2, 16, y2 + 16)
    )
    assert _texts(three) == ["甲", "乙", "丙"]
    assert [line.gap_before for line in three] == [False, False, True]


def test_paragraph_gap_uses_median_line_height():
    # M3: heights 16 / 64 / 16, both gaps are 30; the base is the median height 16.
    assert layout.PARAGRAPH_GAP * 16 < 30 < layout.PARAGRAPH_GAP * 64
    lines = _lines(rect("甲", 0, 0, 16, 16), rect("乙", 0, 46, 64, 110), rect("丙", 0, 140, 16, 156))
    assert _texts(lines) == ["甲", "乙", "丙"]
    assert [line.gap_before for line in lines] == [False, True, True]


def test_linebreak_inside_block_text():
    lines = _lines(rect("ab\ncd\r\nef g", 0, 0, 100, 16))
    assert _texts(lines) == ["ab cd  ef g"]
    assert lines[0].text.splitlines() == [lines[0].text]


@pytest.mark.parametrize("ch", LINE_BREAK_CHARS)
def test_each_linebreak_char_becomes_space(ch):
    # L5: each Q3 char maps to one U+0020.
    assert _texts(_lines(rect("a" + ch + "b", 0, 0, 100, 16))) == ["a b"]


def test_tab_is_not_a_linebreak():
    # L5: only splitlines boundaries are replaced, not every whitespace char.
    assert _texts(_lines(rect("a\tb", 0, 0, 100, 16))) == ["a\tb"]


@pytest.mark.parametrize("bad", ["text", None, [rect("a", 0, 0, 1, 1)]])
def test_rejects_non_result(bad):
    with pytest.raises(TypeError):
        build_lines(bad)


# --- properties --------------------------------------------------------------


def _grid_example(rows, gaps, h=16.0):
    return render_grid(h, (0.0, 0.0), rows, gaps)


@settings(deadline=None)
@given(grid_layouts())
@example(_grid_example([[("甲", 16, 1)], [("乙", 16, 1)]], [layout.PARAGRAPH_GAP * 16]))
@example(_grid_example([[("甲", 16, 1)], [("乙", 16, 1)]], [-0.45 * 16]))
@example(_grid_example([[("a", 16, 1)]], []))
def test_grid_roundtrip(layout_and_expected):
    blocks, expected = layout_and_expected
    lines = build_lines(OcrResult(blocks))
    assert [(line.text, line.gap_before) for line in lines] == expected


@settings(deadline=None)
@given(jittered_rows())
def test_jittered_same_line_splits(rows_and_texts):
    blocks, expected = rows_and_texts
    lines = build_lines(OcrResult(blocks))
    assert len(lines) == len(expected)
    assert _texts(lines) == expected
    assert all(a.top <= b.top for a, b in zip(lines, lines[1:]))


@settings(deadline=None)
@given(st.data())
def test_order_independent(data):
    blocks = data.draw(arbitrary_layouts())
    shuffled = data.draw(st.permutations(blocks))
    assert build_lines(OcrResult(shuffled)) == build_lines(OcrResult(blocks))


@settings(deadline=None)
@given(arbitrary_layouts())
def test_conservation_and_line_shape(blocks):
    lines = build_lines(OcrResult(blocks))
    assert Counter(_nonws("".join(b.text for b in blocks))) == Counter(_nonws("".join(_texts(lines))))
    kept = [b.text.strip() for b in blocks if b.text.strip()]
    for t in kept:
        assert any(t in line.text for line in lines)
    assert len(lines) <= len(kept)
    for line in lines:
        assert line.text and line.text == line.text.strip() and "\n" not in line.text
    if lines:
        assert lines[0].gap_before is False


@settings(deadline=None)
@given(
    arbitrary_layouts(),
    st.integers(-1000, 1000),
    st.integers(-1000, 1000),
    st.sampled_from([0.25, 0.5, 2.0, 4.0, 8.0]),
)
def test_translation_and_scale_invariance(blocks, dx, dy, k):
    moved = tuple(
        TextBlock(b.text, tuple((k * x + dx, k * y + dy) for x, y in b.box), b.score) for b in blocks
    )
    l1 = build_lines(OcrResult(blocks))
    l2 = build_lines(OcrResult(moved))
    assert [(a.text, a.gap_before) for a in l2] == [(a.text, a.gap_before) for a in l1]
    for a, b in zip(l1, l2):
        assert b.left == k * a.left + dx
        assert b.right == k * a.right + dx
        assert b.top == k * a.top + dy
        assert b.bottom == k * a.bottom + dy
