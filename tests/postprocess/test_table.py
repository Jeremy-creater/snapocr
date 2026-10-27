"""M4 WI-13: snapocr.postprocess.table.table_cells (PRD F16-3; unit lane).

Blocks are drawn on a grid: row r spans ``Y0 + r * PITCH`` to ``+ H``;
cells are placed by explicit x ranges so each F16-3 rule (1 to 5) gets a
layout that only that rule resolves.

Laws: every row has the same number of cells; every block text appears in
exactly one cell (texts have no spaces, so a cell splits back into them); a
global shift changes nothing; a clean grid with a full header row and
centred, jittered cells round-trips.
"""

from collections import Counter

from hypothesis import given
from hypothesis import strategies as st

from snapocr.engines.types import OcrResult
from snapocr.postprocess.table import table_cells
from support.pp_strategies import rect

H, PITCH, Y0 = 20.0, 30.0, 10.0


def at(text: str, x0: float, x1: float, row: float) -> object:
    top = Y0 + row * PITCH
    return rect(text, x0, top, x1, top + H)


def table(*blocks) -> list[list[str]]:
    return table_cells(OcrResult(tuple(blocks)))


# --- basics ---------------------------------------------------------------------


def test_empty_result_is_an_empty_table():
    assert table() == []


def test_whitespace_only_blocks_are_ignored():
    assert table(at("  ", 0, 40, 0)) == []


def test_three_by_three_grid():
    blocks = [at(f"r{r}c{c}", c * 100, c * 100 + 40, r) for r in range(3) for c in range(3)]
    assert table(*reversed(blocks)) == [["r0c0", "r0c1", "r0c2"], ["r1c0", "r1c1", "r1c2"], ["r2c0", "r2c1", "r2c2"]]


def test_missing_cell_is_empty():
    assert table(
        at("a", 0, 40, 0), at("b", 100, 140, 0), at("c", 200, 240, 0),
        at("d", 0, 40, 1), at("f", 200, 240, 1),
    ) == [["a", "b", "c"], ["d", "", "f"]]


# --- rule 1: rows follow F2-0 ------------------------------------------------------


def test_rows_tolerate_vertical_jitter():
    # 6 px of a 20 px height off: still more than half overlapping, one row.
    assert table(at("a", 0, 40, 0), rect("b", 100, Y0 + 6, 140, Y0 + 6 + H), at("c", 200, 240, 0)) == [["a", "b", "c"]]


# --- rule 2: which blocks define the columns -----------------------------------------


def test_single_block_row_does_not_join_columns():
    # The title spans columns 1 and 2; it must not glue them together.
    assert table(
        at("Title", 90, 230, 0),
        at("a", 0, 40, 1), at("b", 100, 140, 1), at("c", 200, 240, 1),
        at("d", 0, 40, 2), at("e", 100, 140, 2), at("f", 200, 240, 2),
    ) == [["", "Title", ""], ["a", "b", "c"], ["d", "e", "f"]]


def test_only_single_block_rows_make_one_column():
    assert table(at("one", 0, 40, 0), at("two", 100, 140, 1), at("three", 10, 90, 2)) == [["one"], ["two"], ["three"]]


def test_touching_boxes_stay_separate_columns():
    # Bold header boxes overlap by 4 px, less than half of the narrower (40 px).
    assert table(
        at("No", 0, 44, 0), at("Name", 40, 140, 0),
        at("1", 10, 30, 1), at("Ann", 60, 120, 1),
    ) == [["No", "Name"], ["1", "Ann"]]


def test_half_overlap_joins_a_column():
    # "x" (0-20) and "y" (10-60) overlap by 10 = half of the narrower: one column.
    assert table(
        at("x", 0, 20, 0), at("p", 200, 240, 0),
        at("y", 10, 60, 1), at("q", 200, 240, 1),
    ) == [["x", "p"], ["y", "q"]]


def test_columns_chain_through_overlapping_blocks():
    # "wide" links "left" and "right", which do not overlap each other.
    assert table(
        at("left", 0, 30, 0), at("k", 300, 340, 0),
        at("wide", 0, 60, 1), at("l", 300, 340, 1),
        at("right", 30, 60, 2), at("m", 300, 340, 2),
    ) == [["left", "k"], ["wide", "l"], ["right", "m"]]


# --- rule 3: assigning blocks to columns ------------------------------------------


def test_title_goes_to_the_column_it_overlaps_most():
    assert table(
        at("Title", 120, 300, 0),
        at("a", 0, 40, 1), at("b", 100, 160, 1), at("c", 200, 260, 1),
    ) == [["", "", "Title"], ["a", "b", "c"]]


def test_block_outside_every_column_goes_to_the_nearest():
    assert table(
        at("a", 0, 40, 0), at("b", 100, 140, 0),
        at("note", 170, 200, 1),
    ) == [["a", "b"], ["", "note"]]


def test_blocks_in_one_cell_join_left_to_right_with_a_space():
    assert table(
        at("head", 0, 100, 0), at("x", 200, 240, 0),
        at("two", 50, 90, 1), at("one", 0, 40, 1), at("y", 200, 240, 1),
    ) == [["head", "x"], ["one two", "y"]]


# --- rule 4: complementary columns merge ------------------------------------------


def test_left_header_and_right_numbers_are_one_column():
    # Excel: text left-aligned, numbers right-aligned; the header of a column
    # does not overlap its numbers, and "Cost" touches the quantities.
    assert table(
        at("Items", 0, 50, 0), at("Qty", 180, 270, 0), at("Cost", 373, 417, 0),
        at("Pumpkin", 0, 70, 1), at("1", 357, 376, 1), at("16", 558, 587, 1),
        at("Ginger", 0, 60, 2), at("0.5", 342, 377, 2), at("12", 558, 587, 2),
    ) == [["Items", "Qty", "Cost"], ["Pumpkin", "1", "16"], ["Ginger", "0.5", "12"]]


def test_columns_that_share_a_row_do_not_merge():
    assert table(
        at("a", 0, 40, 0), at("b", 100, 140, 0),
        at("c", 0, 40, 1),
        at("d", 100, 140, 2),
    ) == [["a", "b"], ["c", ""], ["", "d"]]


# --- rule 5: rows of a merged cell ----------------------------------------------------


def _merged_cell_table(offset: float) -> list[list[str]]:
    # "Sales" is a cell merged over rows 1 and 2, drawn ``offset`` below row 1's top.
    top = Y0 + PITCH + offset
    return table(
        at("Dept", 0, 40, 0), at("N", 100, 140, 0), at("V", 200, 240, 0),
        at("1", 100, 140, 1), at("x", 200, 240, 1),
        rect("Sales", 0, top, 40, top + H),
        at("2", 100, 140, 2), at("y", 200, 240, 2),
    )


def test_text_between_two_rows_joins_the_row_it_overlaps_more():
    # 8 px into row 1, 2 px into row 2 (less than half: F2-0 keeps it apart).
    assert _merged_cell_table(12) == [["Dept", "N", "V"], ["Sales", "1", "x"], ["", "2", "y"]]


def test_text_between_rows_closer_to_the_lower_row_joins_it():
    assert _merged_cell_table(18) == [["Dept", "N", "V"], ["", "1", "x"], ["Sales", "2", "y"]]


def test_text_exactly_between_two_rows_joins_the_upper():
    # 5 px into each row: both qualify, the tie goes up.
    assert _merged_cell_table(15) == [["Dept", "N", "V"], ["Sales", "1", "x"], ["", "2", "y"]]


def test_merged_text_qualifying_for_both_rows_joins_the_one_it_overlaps_more():
    # Rows 4 px apart; "Sales" overlaps row 1 by 7 px and row 2 by 9 px (both
    # at least a quarter, both under half of 20 px, so F2-0 keeps three lines).
    assert table(
        rect("Dept", 0, 0, 40, 20), rect("N", 100, 0, 140, 20), rect("V", 200, 0, 240, 20),
        rect("1", 100, 40, 140, 60), rect("x", 200, 40, 240, 60),
        rect("Sales", 0, 53, 40, 73),
        rect("2", 100, 64, 140, 84), rect("y", 200, 64, 240, 84),
    ) == [["Dept", "N", "V"], ["", "1", "x"], ["Sales", "2", "y"]]


def test_overlapping_rows_with_a_shared_column_stay_apart():
    sub = rect("Subtotal", 100, Y0 + 15, 140, Y0 + 15 + H)
    assert table(
        at("1", 0, 40, 0), at("Ann", 100, 140, 0),
        sub,
        at("2", 0, 40, 1), at("Bob", 100, 140, 1),
    ) == [["1", "Ann"], ["", "Subtotal"], ["2", "Bob"]]


def test_rows_that_barely_touch_stay_apart():
    # 4 px of overlap is less than a quarter of the 20 px height.
    low = rect("z", 200, Y0 + 16, 240, Y0 + 16 + H)
    assert table(
        at("a", 0, 40, 0), at("b", 100, 140, 0),
        low,
        at("c", 0, 40, 2), at("d", 100, 140, 2), at("e", 200, 240, 2),
    ) == [["a", "b", ""], ["", "", "z"], ["c", "d", "e"]]


# --- laws -------------------------------------------------------------------------------

words = st.text(alphabet="abcdefghijXYZ0123456789", min_size=1, max_size=6)
raw_block = st.tuples(
    words,
    st.integers(0, 600), st.integers(0, 400),
    st.integers(4, 120), st.integers(4, 40),
)


def _blocks(raw):
    return [rect(t, x, y, x + w, y + h) for t, x, y, w, h in raw]


@given(st.lists(raw_block, max_size=30))
def test_every_row_has_the_same_number_of_cells(raw):
    cells = table(*_blocks(raw))
    assert len({len(row) for row in cells}) <= 1


@given(st.lists(raw_block, max_size=30))
def test_every_text_lands_in_exactly_one_cell(raw):
    cells = table(*_blocks(raw))
    found = Counter(word for row in cells for cell in row for word in cell.split())
    assert found == Counter(t for t, *_ in raw)


@given(st.lists(raw_block, max_size=30), st.integers(-300, 300), st.integers(-300, 300))
def test_a_global_shift_changes_nothing(raw, dx, dy):
    shifted = [(t, x + dx, y + dy, w, h) for t, x, y, w, h in raw]
    assert table(*_blocks(shifted)) == table(*_blocks(raw))


COL_W, COL_GAP = 100, 30


@st.composite
def clean_grid(draw):
    n_cols = draw(st.integers(1, 6))
    n_rows = draw(st.integers(1, 8))
    grid = [[draw(words) for _ in range(n_cols)]]  # full header row
    for _ in range(n_rows - 1):
        grid.append([draw(st.one_of(st.just(""), words)) for _ in range(n_cols)])
    blocks = []
    for r, row in enumerate(grid):
        for c, text in enumerate(row):
            if not text:
                continue
            width = draw(st.integers(20, 90))
            jitter = draw(st.integers(-2, 2))
            x0 = c * (COL_W + COL_GAP) + (COL_W - width) // 2 + jitter
            blocks.append(at(text, x0, x0 + width, r))
    expected = [row for row in grid if any(row)]
    return blocks, expected


@given(clean_grid())
def test_a_clean_grid_round_trips(case):
    blocks, expected = case
    assert table(*blocks) == expected
