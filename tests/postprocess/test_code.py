"""M3 WI-13: snapocr.postprocess.code.code_text (PRD F13-2 to F13-4; unit lane).

Blocks are drawn on a grid: every character is CW wide, every line is H high
and lines start PITCH apart. Texts have at least 3 characters, so the
estimated character width is exactly CW.

Laws: a global translation does not change the output; the non-whitespace
characters are conserved; a clean grid with 4-space levels and blank rows
round-trips (indentation and blank lines), also under +-0.45 character of
horizontal jitter; every indentation is a multiple of 2.
"""

from collections import Counter

from hypothesis import given
from hypothesis import strategies as st

from snapocr.engines.types import OcrResult, TextBlock
from snapocr.postprocess.code import code_text
from support.pp_strategies import rect

CW, H, PITCH = 10.0, 20.0, 30.0
X0, Y0 = 50.0, 40.0


def at(text: str, col: float, row: float, *, x0: float = X0, y0: float = Y0) -> TextBlock:
    left = x0 + col * CW
    top = y0 + row * PITCH
    return rect(text, left, top, left + len(text) * CW, top + H)


def lines(*rows: tuple[str, float]) -> OcrResult:
    """One block per row: (text, column); row i is drawn on grid row i."""
    return OcrResult(tuple(at(text, col, i) for i, (text, col) in enumerate(rows)))


def indents(text: str) -> list[int]:
    return [len(line) - len(line.lstrip(" ")) for line in text.split("\n")]


# --- F13-3 indentation ----------------------------------------------------------


def test_four_space_levels():
    result = lines(("def f():", 0), ("x = 1", 4), ("if x:", 4), ("y = 2", 8), ("return", 4))
    assert code_text(result) == "def f():\n    x = 1\n    if x:\n        y = 2\n    return"


def test_two_space_levels():
    result = lines(("<ul>", 0), ("<li>", 2), ("<b>x</b>", 4), ("</li>", 2), ("</ul>", 0))
    assert code_text(result) == "<ul>\n  <li>\n    <b>x</b>\n  </li>\n</ul>"


def test_continuation_is_rounded_to_the_unit():
    # Most indented lines are multiples of 4, so the unit is 4; 13 -> 12, 15 -> 16.
    result = lines(("foo(", 0), ("aaa,", 4), ("bbb,", 13), ("ccc,", 4), ("ddd)", 15))
    assert indents(code_text(result)) == [0, 4, 12, 4, 16]


def test_half_multiples_of_four_choose_four():
    # One of two indented lines is a multiple of 4: "at least half" -> unit 4; 2 -> 4.
    result = lines(("top", 0), ("two", 2), ("four", 4))
    assert indents(code_text(result)) == [0, 4, 4]


def test_minority_multiples_of_four_choose_two():
    result = lines(("top", 0), ("two", 2), ("two", 2), ("four", 4))
    assert indents(code_text(result)) == [0, 2, 2, 4]


def test_unit_uses_rounded_columns():
    # 3.6 rounds to 4 (a multiple of 4) and 5.6 to 6: one of two -> unit 4, so 5.6 -> 4.
    # Testing the raw offsets instead would find no multiple of 4 and give [0, 4, 6].
    result = lines(("top", 0), ("aaa", 3.6), ("bbb", 5.6))
    assert indents(code_text(result)) == [0, 4, 4]


def test_jitter_below_half_a_character_keeps_indentation():
    # The leftmost line is 0.45 left of the grid, others up to 0.45 right of it.
    result = lines(("top", -0.45), ("aaa", 4.45), ("bbb", 3.6), ("ccc", 8.4), ("end", 0.3))
    assert indents(code_text(result)) == [0, 4, 4, 8, 0]


def test_offset_below_one_character_is_no_indent():
    result = lines(("top", 0), ("aaa", 0.9))
    assert code_text(result) == "top\naaa"


def test_offsets_are_relative_to_the_leftmost_line():
    # The first line is indented: the screenshot started inside a block.
    result = lines(("return x", 4), ("def g():", 0), ("pass", 4))
    assert code_text(result) == "    return x\ndef g():\n    pass"


def test_character_width_ignores_short_blocks():
    # "}" and "x" are 1 char but drawn 30 wide; the median of the >=3-char blocks is CW.
    result = OcrResult((
        at("fn() {", 0, 0),
        rect("x", X0 + 4 * CW, Y0 + PITCH, X0 + 7 * CW, Y0 + PITCH + H),
        at("abc", 4, 2),
        rect("}", X0, Y0 + 3 * PITCH, X0 + 3 * CW, Y0 + 3 * PITCH + H),
    ))
    assert code_text(result) == "fn() {\n    x\n    abc\n}"


def test_character_width_from_all_blocks_when_all_are_short():
    # Every block is 2 chars, 20 wide: width 10 per char, so x offset 40 is 4 columns.
    result = OcrResult((
        rect("ab", X0, Y0, X0 + 20, Y0 + H),
        rect("cd", X0 + 40, Y0 + PITCH, X0 + 60, Y0 + PITCH + H),
        rect("ef", X0 + 40, Y0 + 2 * PITCH, X0 + 60, Y0 + 2 * PITCH + H),
    ))
    assert code_text(result) == "ab\n    cd\n    ef"


def test_zero_width_blocks_give_no_indentation():
    result = OcrResult((
        rect("abc", X0, Y0, X0, Y0 + H),
        rect("def", X0 + 40, Y0 + PITCH, X0 + 40, Y0 + PITCH + H),
        rect("ghi", X0 + 80, Y0 + PITCH, X0 + 80, Y0 + PITCH + H),
    ))
    assert code_text(result) == "abc\ndef ghi"


# --- F13-2 one output line per visual line ----------------------------------------


def test_spaces_between_blocks_follow_the_gap():
    # "x = f()" ends at column 11; the comment starts at 13 -> 2 spaces.
    result = OcrResult((at("x = f()", 4, 0), at("# note", 13, 0)))
    assert code_text(result) == "x = f()  # note"


def test_gap_rounds_half_up():
    # The gap is 2.5 columns -> 3 spaces (not banker's rounding to 2).
    result = OcrResult((at("abc", 0, 0), at("def", 5.5, 0)))
    assert code_text(result) == "abc   def"


def test_small_or_negative_gap_is_one_space():
    result = OcrResult((at("abc", 0, 0), at("def", 3.2, 0), at("ghi", 6.0, 0)))
    assert code_text(result) == "abc def ghi"


def test_blocks_in_a_line_are_joined_left_to_right():
    result = OcrResult((at("bbb", 5, 0), at("aaa", 0, 0), at("zzz", 4, 1)))
    assert code_text(result) == "aaa  bbb\n    zzz"


def test_no_prose_rules():
    # No paragraph merge, no CJK/Latin spacing, no full-width punctuation, no CJK seam rule.
    result = lines(("print('中文abc')", 0), ("x = 1, 2", 4), ("# 注释:ok", 4))
    out = code_text(result)
    assert out == "print('中文abc')\n    x = 1, 2\n    # 注释:ok"


def test_cjk_blocks_keep_the_gap_spaces():
    result = OcrResult((at("s = 1", 0, 0), at("# 中文", 7, 0)))
    assert code_text(result) == "s = 1  # 中文"


# --- F13-4 blank lines ----------------------------------------------------------


def test_blank_lines_follow_the_vertical_gaps():
    rows = [("aaa", 0, 0), ("bbb", 0, 1), ("ccc", 4, 2), ("ddd", 4, 3), ("eee", 0, 5), ("fff", 0, 8)]
    result = OcrResult(tuple(at(t, c, r) for t, c, r in rows))
    assert code_text(result) == "aaa\nbbb\n    ccc\n    ddd\n\neee\n\n\nfff"


def test_blank_line_count_rounds_half_up():
    # Gaps of 1, 1, 1 rows set the pitch; a 2.5-row gap -> round(2.5) - 1 = 2 blank lines.
    rows = [("aaa", 0), ("bbb", 1), ("ccc", 2), ("ddd", 3), ("eee", 5.5)]
    result = OcrResult(tuple(at(t, 0, r) for t, r in rows))
    assert code_text(result) == "aaa\nbbb\nccc\nddd\n\n\neee"


def test_slightly_wide_gap_is_no_blank_line():
    rows = [("aaa", 0), ("bbb", 1), ("ccc", 2.4), ("ddd", 3.4)]
    result = OcrResult(tuple(at(t, 0, r) for t, r in rows))
    assert code_text(result) == "aaa\nbbb\nccc\nddd"


def test_single_line_is_plain_text():
    assert code_text(OcrResult((at("only one", 7, 3),))) == "only one"


def test_empty_and_whitespace_only_results_are_empty():
    assert code_text(OcrResult(())) == ""
    assert code_text(OcrResult((rect("  ", 0, 0, 30, 20), rect("\n", 0, 40, 30, 60)))) == ""


def test_line_breaks_inside_a_block_become_spaces():
    # Same normalization as F2-0 (Q3): one block never becomes two output lines.
    assert code_text(OcrResult((at("a\nb c", 0, 0),))) == "a b c"


# --- laws -----------------------------------------------------------------------

_word = st.text(alphabet="abcdefghijklmnopqrstuvwxyz=().:_", min_size=3, max_size=8)


@st.composite
def code_grids(draw):
    """Rows of (level, text), 4 spaces per level, at least one indented row.

    Row gaps are 1 for more than half of the rows, so the pitch is exact.
    Returns (rows, gaps, expected_text) with gaps[i] = grid rows before row i+1.
    """
    n = draw(st.integers(2, 12))
    others = draw(st.lists(st.integers(0, 4), min_size=n - 2, max_size=n - 2))
    levels = draw(st.permutations(others + [0, draw(st.integers(1, 4))]))
    texts = draw(st.lists(_word, min_size=n, max_size=n))
    wide = draw(st.lists(st.integers(2, 4), max_size=(n - 2) // 2))
    gaps = draw(st.permutations(wide + [1] * (n - 1 - len(wide))))
    expected = [" " * (4 * levels[0]) + texts[0]]
    for i in range(1, n):
        expected.extend([""] * (gaps[i - 1] - 1))
        expected.append(" " * (4 * levels[i]) + texts[i])
    return list(zip(levels, texts)), gaps, "\n".join(expected)


def _draw(rows, gaps, jitter=None, dx=0.0, dy=0.0):
    blocks, row = [], 0
    for i, (level, text) in enumerate(rows):
        if i:
            row += gaps[i - 1]
        shift = jitter[i] if jitter else 0.0
        blocks.append(at(text, 4 * level + shift, row, x0=X0 + dx, y0=Y0 + dy))
    return OcrResult(tuple(blocks))


@given(code_grids())
def test_clean_grid_round_trips(grid):
    rows, gaps, expected = grid
    assert code_text(_draw(rows, gaps)) == expected


@given(code_grids(), st.data())
def test_horizontal_jitter_below_half_a_character_round_trips(grid, data):
    rows, gaps, expected = grid
    # Pairwise differences stay below 0.9 column: the leftmost row may be the shifted one.
    jitter = data.draw(st.lists(st.sampled_from([-0.45, -0.25, 0.0, 0.25, 0.45]), min_size=len(rows), max_size=len(rows)))
    assert code_text(_draw(rows, gaps, jitter)) == expected


@given(code_grids(), st.integers(-500, 500), st.integers(-500, 500))
def test_translation_does_not_change_the_output(grid, dx, dy):
    rows, gaps, _ = grid
    assert code_text(_draw(rows, gaps, dx=float(dx), dy=float(dy))) == code_text(_draw(rows, gaps))


@given(st.lists(st.tuples(_word, st.floats(0, 20), st.integers(0, 6)), min_size=1, max_size=10))
def test_characters_are_conserved_and_indents_are_even(cells):
    # Several blocks may share a grid row; columns are arbitrary.
    blocks = []
    for text, col, row in cells:
        blocks.append(at(text, col, row))
    out = code_text(OcrResult(tuple(blocks)))
    assert Counter("".join(out.split())) == Counter("".join(t for t, _, _ in cells))
    assert all(n % 2 == 0 for n in indents(out))
