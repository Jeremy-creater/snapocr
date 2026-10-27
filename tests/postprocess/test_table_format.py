"""M4 WI-14: Markdown and HTML for a cell grid (PRD F16-2; unit lane).

Laws: the Markdown has one line per row plus the separator, and every line
splits back into the escaped cells; the HTML holds every cell text once,
escaped, in row order.
"""

import html
import re

from hypothesis import given
from hypothesis import strategies as st

from snapocr.postprocess.table import to_html, to_markdown

# --- Markdown -----------------------------------------------------------------------


def test_markdown_first_row_is_the_header():
    assert to_markdown([["Name", "Qty"], ["Apple", "3"], ["Pear", "5"]]) == (
        "| Name | Qty |\n| --- | --- |\n| Apple | 3 |\n| Pear | 5 |"
    )


def test_markdown_single_row_is_a_header_only():
    assert to_markdown([["a", "b", "c"]]) == "| a | b | c |\n| --- | --- | --- |"


def test_markdown_empty_cells():
    assert to_markdown([["a", ""], ["", "d"]]) == "| a |  |\n| --- | --- |\n|  | d |"


def test_markdown_escapes_pipes():
    assert to_markdown([["a|b", "c"]]) == "| a\\|b | c |\n| --- | --- |"


def test_markdown_line_breaks_become_spaces():
    assert to_markdown([["x\ny", "p\r\nq", "m\rn"]]) == "| x y | p q | m n |\n| --- | --- | --- |"


def test_markdown_of_nothing_is_empty():
    assert to_markdown([]) == ""


# --- HTML -----------------------------------------------------------------------------


def test_html_table():
    assert to_html([["Name", "Qty"], ["Apple", ""]]) == (
        "<table>\n<tr><td>Name</td><td>Qty</td></tr>\n<tr><td>Apple</td><td></td></tr>\n</table>"
    )


def test_html_escapes_markup():
    assert to_html([['<b>&"x"</b>']]) == "<table>\n<tr><td>&lt;b&gt;&amp;&quot;x&quot;&lt;/b&gt;</td></tr>\n</table>"


def test_html_of_nothing_is_empty():
    assert to_html([]) == ""


# --- laws -----------------------------------------------------------------------------

cell = st.text(alphabet="ab|<>&\" 中\n", max_size=5)


@st.composite
def grids(draw):
    n_cols = draw(st.integers(1, 4))
    return draw(st.lists(st.lists(cell, min_size=n_cols, max_size=n_cols), min_size=1, max_size=5))


def _md_cell(text: str) -> str:
    return text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ").replace("|", "\\|")


@given(grids())
def test_markdown_lines_split_back_into_cells(grid):
    lines = to_markdown(grid).split("\n")
    assert len(lines) == len(grid) + 1
    assert lines[1] == "|" + " --- |" * len(grid[0])
    for line, row in zip([lines[0], *lines[2:]], grid):
        parts = re.split(r"(?<!\\)\|", line)
        assert parts[0] == parts[-1] == ""
        assert [p[1:-1] for p in parts[1:-1]] == [_md_cell(c) for c in row]


@given(grids())
def test_html_holds_every_cell_in_order(grid):
    found = re.findall(r"<td>(.*?)</td>", to_html(grid), flags=re.S)
    assert [html.unescape(f) for f in found] == [c for row in grid for c in row]
    assert to_html(grid).count("<tr>") == len(grid)
