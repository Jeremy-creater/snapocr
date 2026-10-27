"""F16-3 table layout (M4 WI-13): OCR blocks into a grid of cell texts.

``table_cells`` turns an ``OcrResult`` into rows of equally many cells. The
rules were fitted to the real OCR boxes of the M4 table screenshots (plan D19):

1. Rows are the F2-0 lines (``layout.group_blocks``).
2. Columns come from the blocks of rows with at least two blocks (a title or
   subtotal row alone would glue columns together); when every row has one
   block, from all blocks. Two blocks are in one column when their horizontal
   overlap is at least ``SAME_COLUMN_OVERLAP`` times the narrower width;
   connected blocks form a column whose span is their horizontal hull.
3. Every block goes to the column it overlaps most (ties and no overlap at
   all: the nearest centre). Blocks of one cell are joined left to right with
   one space; missing cells are "".
4. Neighbouring columns that never both hold text in one row merge, left to
   right (spreadsheet headers are left-aligned, numbers right-aligned).
5. Neighbouring rows that overlap vertically by at least ``SAME_ROW_OVERLAP``
   times the shorter height and have no column in common merge (text of a
   cell merged over two rows); the pair with the most overlap goes first, so
   such a text joins the row it overlaps more. Ties go to the upper pair.

Last, ``strip_sheet_headers`` removes spreadsheet column letters and row
numbers (F16-5). ``to_markdown`` and ``to_html`` give the two clipboard forms
(F16-2).
"""

from __future__ import annotations

import html
import re

from snapocr.engines.types import OcrResult
from snapocr.postprocess.layout import group_blocks

SAME_COLUMN_OVERLAP = 0.5
SAME_ROW_OVERLAP = 0.25

_COLUMN_LETTERS = re.compile(r"[A-Z]{1,2}")
_ROW_NUMBER = re.compile(r"[0-9]+")

# group_blocks' normalized block: (center_y, top, bottom, left, right, text, score).
_Block = tuple[float, float, float, float, float, str, float]
_Span = tuple[float, float]


def _overlap(a: _Span, b: _Span) -> float:
    return min(a[1], b[1]) - max(a[0], b[0])


def _columns(blocks: list[_Block]) -> list[_Span]:
    """Rule 2: the spans of the connected groups of ``blocks``, sorted left to right."""
    parent = list(range(len(blocks)))

    def root(i: int) -> int:
        while parent[i] != i:
            i = parent[i]
        return i

    for i, a in enumerate(blocks):
        for j in range(i):
            b = blocks[j]
            narrower = min(a[4] - a[3], b[4] - b[3])
            if _overlap((a[3], a[4]), (b[3], b[4])) >= SAME_COLUMN_OVERLAP * narrower:
                parent[root(i)] = root(j)
    spans: dict[int, _Span] = {}
    for i, b in enumerate(blocks):
        left, right = spans.get(root(i), (b[3], b[4]))
        spans[root(i)] = (min(left, b[3]), max(right, b[4]))
    return sorted(spans.values())


def _column_of(block: _Block, columns: list[_Span]) -> int:
    """Rule 3: most overlap, then nearest centre."""
    span = (block[3], block[4])
    centre = (block[3] + block[4]) / 2

    def key(c: int) -> tuple[float, float]:
        left, right = columns[c]
        return max(0.0, _overlap(span, columns[c])), -abs(centre - (left + right) / 2)

    return max(range(len(columns)), key=key)


# A row while it is being built: column -> blocks, and its vertical extent.
_Row = tuple[dict[int, list[_Block]], float, float]


def _merge_columns(rows: list[_Row], count: int) -> list[_Row]:
    """Rule 4: renumber the columns after merging complementary neighbours."""
    target = [0] * count
    group = {0}
    for c in range(1, count):
        if any(any(g in cells for g in group) and c in cells for cells, _, _ in rows):
            target[c] = target[c - 1] + 1
            group = {c}
        else:
            target[c] = target[c - 1]
            group.add(c)
    merged: list[_Row] = []
    for cells, top, bottom in rows:
        out: dict[int, list[_Block]] = {}
        for c, blocks in cells.items():
            out.setdefault(target[c], []).extend(blocks)
        merged.append((out, top, bottom))
    return merged


def _pair_overlap(upper: _Row, lower: _Row) -> float | None:
    """How much two neighbouring rows overlap when rule 5 lets them merge, else None."""
    cells, top, bottom = upper
    other, top2, bottom2 = lower
    overlap = _overlap((top, bottom), (top2, bottom2))
    shorter = min(bottom - top, bottom2 - top2)
    if overlap > 0 and overlap >= SAME_ROW_OVERLAP * shorter and not cells.keys() & other.keys():
        return overlap
    return None


def _merge_rows(rows: list[_Row]) -> list[_Row]:
    """Rule 5: merge the pair with the most overlap first (ties: the upper pair), until none is left."""
    rows = list(rows)
    while True:
        pairs = [(o, -i) for i in range(len(rows) - 1) if (o := _pair_overlap(rows[i], rows[i + 1])) is not None]
        if not pairs:
            return rows
        i = -max(pairs)[1]
        (cells, top, bottom), (other, top2, bottom2) = rows[i], rows[i + 1]
        rows[i : i + 2] = [({**cells, **other}, min(top, top2), max(bottom, bottom2))]


def table_cells(result: OcrResult) -> list[list[str]]:
    """The cell texts of ``result``, top to bottom (see module doc)."""
    groups = group_blocks(result)
    if not groups:
        return []
    multi = [b for g in groups if len(g) >= 2 for b in g]
    columns = _columns(multi or [b for g in groups for b in g])
    rows: list[_Row] = []
    for group in groups:
        cells: dict[int, list[_Block]] = {}
        for block in group:
            cells.setdefault(_column_of(block, columns), []).append(block)
        rows.append((cells, min(b[1] for b in group), max(b[2] for b in group)))
    rows = _merge_rows(_merge_columns(rows, len(columns)))
    width = 1 + max(c for cells, _, _ in rows for c in cells)
    return strip_sheet_headers([
        [" ".join(b[5] for b in sorted(cells.get(c, []), key=lambda b: (b[3], b[4], b[5]))) for c in range(width)]
        for cells, _, _ in rows
    ])


def _column_number(letters: str) -> int:
    """Spreadsheet column number: A = 1, Z = 26, AA = 27."""
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - ord("A") + 1
    return n


def _is_letter_row(row: list[str]) -> bool:
    """At least two cells of 1-2 capitals whose column numbers step with their positions."""
    filled = [(i, text) for i, text in enumerate(row) if text]
    if len(filled) < 2 or not all(_COLUMN_LETTERS.fullmatch(text) for _, text in filled):
        return False
    i0, first = filled[0]
    return all(_column_number(text) - _column_number(first) == i - i0 for i, text in filled)


def strip_sheet_headers(cells: list[list[str]]) -> list[list[str]]:
    """F16-5: drop a first row of column letters and, below an empty corner, a column of row numbers."""
    if not cells or not _is_letter_row(cells[0]):
        return cells
    corner, rest = cells[0][0], cells[1:]
    numbers = [row[0] for row in rest if row[0]]
    if not corner and numbers and 2 * sum(bool(_ROW_NUMBER.fullmatch(n)) for n in numbers) >= len(numbers):
        return [row[1:] for row in rest]
    return rest


def _markdown_cell(text: str) -> str:
    return text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ").replace("|", "\\|")


def to_markdown(cells: list[list[str]]) -> str:
    """F16-2: a Markdown table; the first row is the header. "" for no rows."""
    if not cells:
        return ""
    lines = ["| " + " | ".join(_markdown_cell(c) for c in row) + " |" for row in cells]
    lines.insert(1, "|" + " --- |" * len(cells[0]))
    return "\n".join(lines)


def to_html(cells: list[list[str]]) -> str:
    """F16-2: an HTML ``<table>`` with every cell escaped. "" for no rows."""
    if not cells:
        return ""
    rows = ["<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in row) + "</tr>" for row in cells]
    return "\n".join(["<table>", *rows, "</table>"])
