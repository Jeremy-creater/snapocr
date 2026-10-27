"""M4 WI-20: spreadsheet column letters and row numbers are removed (PRD F16-5; unit lane).

``strip_sheet_headers`` works on the cell grid; ``table_cells`` applies it last.
"""

from snapocr.engines.types import OcrResult
from snapocr.postprocess.table import strip_sheet_headers, table_cells
from support.pp_strategies import rect


def test_letters_and_row_numbers_are_removed():
    assert strip_sheet_headers([
        ["", "A", "B", "C"],
        ["1", "Name", "Dept", "Sales"],
        ["2", "Ann", "IT", "300"],
    ]) == [["Name", "Dept", "Sales"], ["Ann", "IT", "300"]]


def test_rows_left_empty_are_kept():
    assert strip_sheet_headers([
        ["", "A", "B"],
        ["1", "x", "y"],
        ["2", "", ""],
        ["3", "z", ""],
    ]) == [["x", "y"], ["", ""], ["z", ""]]


def test_columns_left_empty_are_kept():
    assert strip_sheet_headers([
        ["", "A", "B", "C"],
        ["1", "x", "", "y"],
    ]) == [["x", "", "y"]]


def test_a_letter_that_was_not_recognized_is_allowed():
    assert strip_sheet_headers([
        ["", "A", "", "C"],
        ["1", "x", "m", "y"],
    ]) == [["x", "m", "y"]]


def test_two_letter_columns():
    assert strip_sheet_headers([
        ["", "Y", "Z", "AA", "AB"],
        ["7", "p", "q", "r", "s"],
    ]) == [["p", "q", "r", "s"]]


def test_a_misread_row_number_still_counts():
    # One of three row numbers came out as "1."; two of three are digits.
    assert strip_sheet_headers([
        ["", "A", "B"],
        ["1.", "x", "y"],
        ["2", "p", "q"],
        ["3", "r", "s"],
    ]) == [["x", "y"], ["p", "q"], ["r", "s"]]


def test_without_row_numbers_only_the_letter_row_goes():
    # The screenshot starts at column A: the corner cell holds "A".
    assert strip_sheet_headers([
        ["A", "B", "C"],
        ["Name", "Dept", "Sales"],
    ]) == [["Name", "Dept", "Sales"]]


def test_first_column_of_words_is_not_row_numbers():
    assert strip_sheet_headers([
        ["", "B", "C"],
        ["Total", "x", "y"],
        ["Sum", "p", "q"],
        ["3", "r", "s"],
    ]) == [["Total", "x", "y"], ["Sum", "p", "q"], ["3", "r", "s"]]


def test_numbered_first_column_without_letters_stays():
    table = [["No", "Name"], ["1", "Ann"], ["2", "Bob"]]
    assert strip_sheet_headers(table) == table


def test_a_single_letter_is_not_a_letter_row():
    table = [["", "A", ""], ["1", "x", "y"]]
    assert strip_sheet_headers(table) == table


def test_upper_case_words_are_not_column_letters():
    table = [["ID", "NO"], ["7", "x"]]
    assert strip_sheet_headers(table) == table


def test_letters_out_of_order_are_not_a_letter_row():
    table = [["", "B", "A"], ["1", "x", "y"]]
    assert strip_sheet_headers(table) == table


def test_letters_that_skip_a_column_are_not_a_letter_row():
    table = [["", "A", "C"], ["1", "x", "y"]]
    assert strip_sheet_headers(table) == table


def test_lower_case_letters_are_not_a_letter_row():
    table = [["", "a", "b"], ["1", "x", "y"]]
    assert strip_sheet_headers(table) == table


def test_only_a_letter_row_leaves_nothing():
    assert strip_sheet_headers([["", "A", "B"]]) == []


def test_empty_table():
    assert strip_sheet_headers([]) == []


def test_table_cells_strips_headers():
    def at(text, x0, row):
        return rect(text, x0, row * 30, x0 + 20, row * 30 + 20)

    result = OcrResult((
        at("A", 100, 0), at("B", 200, 0),
        at("1", 0, 1), at("Name", 100, 1), at("Dept", 200, 1),
        at("2", 0, 2), at("Ann", 100, 2), at("IT", 200, 2),
    ))
    assert table_cells(result) == [["Name", "Dept"], ["Ann", "IT"]]
