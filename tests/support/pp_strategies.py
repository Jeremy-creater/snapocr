"""Shared Hypothesis strategies for the F2 post-processing tests.

Matrix: .claude/tdd-guardian/tests-20261025-183000.md, section "共享生成器"
(``cjk`` uses the revision-1 L10 widened version). Paragraph generators are
added by the work item that needs them.
"""

import math
from collections.abc import Sequence
from string import ascii_letters, digits

from hypothesis import strategies as st

from snapocr.engines.types import TextBlock
from snapocr.postprocess.chars import is_cjk, is_cjk_punct
from snapocr.postprocess.layout import PARAGRAPH_GAP, Line

# L10: unified ideographs (start and end of the block) plus extension A.
cjk = st.one_of(
    st.characters(min_codepoint=0x4E00, max_codepoint=0x4FFF),
    st.characters(min_codepoint=0x3400, max_codepoint=0x4DBF),
    st.characters(min_codepoint=0x9F00, max_codepoint=0x9FFF),
)
latin = st.sampled_from(ascii_letters + digits)
fw_punct = st.sampled_from("，。！？：；、「」（）")
ascii_punct = st.sampled_from(",.;:?!-")

# Fragments that can trigger (or partly trigger) a protected span.
SPAN_FRAGMENTS = ("https://", "http://", "www.", "@", "`", "C:\\", "D:\\资料\\", ".com", "/", "a.b@x.org")
span_fragments = st.sampled_from(SPAN_FRAGMENTS)


def mixed_text(max_size: int = 40, *, with_fragments: bool = True) -> st.SearchStrategy[str]:
    """Mixed CJK / Latin / punctuation / whitespace text, optionally with span fragments."""
    parts = [cjk, cjk, latin, latin, st.just(" "), st.just("\n"), fw_punct, ascii_punct]
    if with_fragments:
        parts.append(span_fragments)
    return st.lists(st.one_of(*parts), max_size=max_size).map("".join)


# ---------------------------------------------------------------------------
# WI-2 layout generators (matrix "共享生成器": block_text, grid_layouts,
# jittered_rows, arbitrary_layouts). Coordinates are multiples of 0.25 (grid)
# or 0.5 (arbitrary), so translations by integers and scalings by powers of 2
# are exact and outputs can be compared with ``==``.
# ---------------------------------------------------------------------------


_block_char = st.one_of(cjk, latin, fw_punct, ascii_punct)


def _seam_join(left: str, right: str) -> str:
    """Test-side Q11 seam: no separator when either side is Han or full-width punct."""
    a, b = left[-1], right[0]
    if is_cjk(a) or is_cjk_punct(a) or is_cjk(b) or is_cjk_punct(b):
        return left + right
    return left + " " + right


def join_row(texts: Sequence[str]) -> str:
    out = texts[0]
    for t in texts[1:]:
        out = _seam_join(out, t)
    return out


@st.composite
def block_text(draw) -> str:
    """1-8 chars of cjk / latin / fw_punct / ascii_punct, inner single spaces only."""
    chars = draw(st.lists(_block_char, min_size=1, max_size=8))
    spaces = draw(st.lists(st.booleans(), min_size=len(chars) - 1, max_size=len(chars) - 1))
    out = chars[0]
    for c, sp in zip(chars[1:], spaces):
        out += (" " if sp else "") + c
    return out[:8].rstrip()


def _quarters(lo: float, hi: float) -> st.SearchStrategy[float]:
    return st.integers(math.ceil(lo * 4), math.floor(hi * 4)).map(lambda n: n / 4)


def rect(text: str, x0: float, y0: float, x1: float, y1: float, score: float = 0.9) -> TextBlock:
    return TextBlock(text, ((x0, y0), (x1, y0), (x1, y1), (x0, y1)), score)


def render_grid(h, origin, rows, row_gaps, jitter=None):
    """Render rows of ``(text, width, hgap_after)`` into blocks.

    Returns ``(blocks, expected)`` with ``expected = [(row_text, gap_before)]``;
    ``gap_before`` is ``row_gap > PARAGRAPH_GAP * h`` (every row has height h).
    ``jitter[i][j]`` (optional) shifts block j of row i vertically.
    """
    ox, oy = origin
    blocks, expected = [], []
    y = oy
    for i, row in enumerate(rows):
        x = ox
        for j, (text, w, hgap) in enumerate(row):
            dy = jitter[i][j] if jitter else 0.0
            blocks.append(rect(text, x, y + dy, x + w, y + dy + h))
            x += w + hgap
        gap = i > 0 and row_gaps[i - 1] > PARAGRAPH_GAP * h
        expected.append((join_row([t for t, _, _ in row]), gap))
        if i < len(rows) - 1:
            y += h + row_gaps[i]
    return blocks, expected


def _rows(draw, h, n_rows):
    cell = st.tuples(block_text(), _quarters(0.25 * h, 20 * h), _quarters(0.25, 4 * h))
    return [draw(st.lists(cell, min_size=1, max_size=4)) for _ in range(n_rows)]


@st.composite
def grid_layouts(draw):
    """``(shuffled blocks, [(row_text, gap_before)])`` for a clean row grid."""
    h = draw(st.sampled_from([16.0, 32.0]))
    n_rows = draw(st.integers(1, 6))
    rows = _rows(draw, h, n_rows)
    row_gap = st.one_of(
        _quarters(-0.45 * h, 0),  # vertical overlap < 0.5h: must NOT merge
        _quarters(0.25 * h, 1.25 * h),
        st.sampled_from([PARAGRAPH_GAP * h, PARAGRAPH_GAP * h + 0.25]),
        _quarters(1.75 * h, 5 * h),
    )
    gaps = [draw(row_gap) for _ in range(n_rows - 1)]
    origin = (draw(_quarters(0, 2000)), draw(_quarters(0, 2000)))
    blocks, expected = render_grid(h, origin, rows, gaps)
    return tuple(draw(st.permutations(blocks))), expected


@st.composite
def jittered_rows(draw):
    """``(shuffled blocks, [row_text])``: grid rows with per-block top jitter <= 0.25h."""
    h = draw(st.sampled_from([16.0, 32.0]))
    n_rows = draw(st.integers(1, 6))
    rows = _rows(draw, h, n_rows)
    gaps = [draw(_quarters(0.75 * h, 5 * h)) for _ in range(n_rows - 1)]
    offsets = st.sampled_from([0.0, 0.125 * h, -0.125 * h, 0.25 * h, -0.25 * h])
    jitter = [[draw(offsets) for _ in row] for row in rows]
    origin = (draw(_quarters(0, 2000)), draw(_quarters(0, 2000)))
    blocks, expected = render_grid(h, origin, rows, gaps, jitter)
    return tuple(draw(st.permutations(blocks))), [t for t, _ in expected]


def _halves(lo: float, hi: float) -> st.SearchStrategy[float]:
    return st.integers(int(lo * 2), int(hi * 2)).map(lambda n: n / 2)


_WHITESPACE_TEXTS = (" ", "\t", "  ", "　", " \t ")


@st.composite
def _arbitrary_block(draw) -> TextBlock:
    x, y = draw(_halves(0, 500)), draw(_halves(0, 500))
    w = draw(_halves(0, 120))
    kind = draw(st.integers(0, 9))
    if kind == 0:
        h = 0.0  # ~10% zero height
    elif kind == 1:
        h = draw(_halves(60, 120))  # tall block
    else:
        h = draw(_halves(0, 120))
    pts = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
    if draw(st.integers(0, 4)) == 0:  # ~20% irregular quadrilateral
        pts = [(px + draw(_halves(-10, 10)), py + draw(_halves(-10, 10))) for px, py in pts]
    if draw(st.integers(0, 9)) == 0:
        text = draw(st.sampled_from(_WHITESPACE_TEXTS))
    else:
        text = draw(block_text())
    return TextBlock(text, tuple(pts), draw(st.integers(0, 20)) / 20)


@st.composite
def arbitrary_layouts(draw) -> tuple[TextBlock, ...]:
    """0-30 unconstrained blocks: zero-height, tall, irregular, blank and duplicate ones."""
    blocks = draw(st.lists(_arbitrary_block(), max_size=30))
    for i in range(1, len(blocks)):
        if draw(st.integers(0, 9)) == 0:  # ~10% exact copy of an earlier block
            blocks[i] = blocks[draw(st.integers(0, i - 1))]
    return tuple(blocks)


# ---------------------------------------------------------------------------
# WI-3 paragraph generators (matrix "共享生成器": labeled_paragraph_lines,
# rev 1 M4 end kinds). The expected merge result is computed from the LABELS
# drawn here -- never by calling the production regexes or ``seam_join``.
# ---------------------------------------------------------------------------

SENTENCE_END_PUNCT = "。！？!?.：:；;…"
_LABEL_CLOSERS = "」”\"）"  # closers drawn after sentence-end punctuation
_M4_CLOSERS = "》」）"  # closers drawn after a Han char: NOT a sentence end (M4)
_letters = st.sampled_from(ascii_letters)


def paragraph_seam_join(left: str, right: str) -> str:
    """Test-side F2-3 seam: Q11 plus "ASCII letter + '-' at the end: no separator"."""
    if len(left) >= 2 and left[-1] == "-" and left[-2] in ascii_letters:
        return left + right
    return _seam_join(left, right)


def _start_kinds() -> st.SearchStrategy[tuple[str, bool]]:
    """``(line prefix, is_list_item)`` per the matrix ``start_kind`` labels (Q7)."""
    fixed_lists = ["- ", "* ", "•", "1. ", "1) ", "1、", "(1)", "（1）", "一、"]
    return st.one_of(
        cjk.map(lambda c: (c, False)),
        _letters.map(lambda c: (c, False)),
        st.sampled_from(fixed_lists).map(lambda s: (s, True)),
        st.integers(0, 19).map(lambda n: (chr(0x2460 + n), True)),  # circled 1..20
        st.just(("1.5倍", False)),
    )


def _end_kinds() -> st.SearchStrategy[tuple[str, bool]]:
    """``(line suffix, is_sentence_end)`` per the matrix ``end_kind`` labels (Q7, M4)."""
    closers = st.lists(st.sampled_from(_LABEL_CLOSERS), min_size=1, max_size=2).map("".join)
    return st.one_of(
        cjk.map(lambda c: (c, False)),
        _letters.map(lambda c: (c, False)),
        _letters.map(lambda c: (c + "-", False)),
        st.just(("，", False)),
        st.sampled_from(digits).map(lambda c: (c, False)),
        st.sampled_from(SENTENCE_END_PUNCT).map(lambda p: (p, True)),
        st.tuples(st.sampled_from(SENTENCE_END_PUNCT), closers).map(lambda t: (t[0] + t[1], True)),
        st.tuples(cjk, st.sampled_from(_M4_CLOSERS)).map(lambda t: (t[0] + t[1], False)),
    )


@st.composite
def _middle(draw) -> str:
    """1-6 cjk / latin tokens with optional single spaces; head and tail are Han or a letter."""
    edge = st.one_of(cjk, _letters)
    inner = st.lists(st.one_of(cjk, latin), max_size=4)
    tokens = [draw(edge), *draw(inner)]
    if draw(st.booleans()):
        tokens.append(draw(edge))
    out = tokens[0]
    for t in tokens[1:]:
        out += (" " if draw(st.booleans()) else "") + t
    return out


@st.composite
def labeled_paragraph_lines(draw, W: float = 512.0, ratio: float = 0.85):
    """``(lines, expected)`` for region ``(0, W)`` and ``full_ratio=ratio``.

    1-8 lines, ``left=0``. ``right_kind``: full ``W``, critical ``ratio*W``,
    just short ``ratio*W - 0.25``, short ``0.5*W``. ``expected`` is the merge
    result derived from the labels: a new group starts at line 0 and at every
    i with ``gap_i or list(start_i) or sentence_end(end_{i-1}) or not
    full(right_{i-1})``.
    """
    n = draw(st.integers(1, 8))
    rights = [(W, True), (ratio * W, True), (ratio * W - 0.25, False), (0.5 * W, False)]
    lines, labels = [], []
    for i in range(n):
        start, is_list = draw(_start_kinds())
        end, is_end = draw(_end_kinds())
        right, is_full = draw(st.sampled_from(rights))
        gap = draw(st.integers(0, 9)) < 3
        text = start + draw(_middle()) + end
        lines.append(Line(text, 0.0, right, 20.0 * i, 20.0 * i + 16, gap))
        labels.append((is_list, is_end, is_full))
    groups: list[list[Line]] = []
    for i, line in enumerate(lines):
        split = i == 0 or line.gap_before or labels[i][0] or labels[i - 1][1] or not labels[i - 1][2]
        if split:
            groups.append([line])
        else:
            groups[-1].append(line)
    expected = []
    for g in groups:
        text = g[0].text
        for member in g[1:]:
            text = paragraph_seam_join(text, member.text)
        expected.append(Line(text, g[0].left, g[-1].right, g[0].top, g[-1].bottom, g[0].gap_before))
    return tuple(lines), tuple(expected)


@st.composite
def free_right_lines(draw, W: int = 512):
    """Labeled lines whose ``right`` is, per line, either kept or any integer in [1, W]."""
    lines, _ = draw(labeled_paragraph_lines(float(W)))
    out = []
    for line in lines:
        if draw(st.booleans()):
            line = Line(line.text, line.left, float(draw(st.integers(1, W))), line.top, line.bottom, line.gap_before)
        out.append(line)
    return tuple(out)
