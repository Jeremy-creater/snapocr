"""F2 WI-6: snapocr.postprocess.pipeline (unit lane).

Law: the text rule chain (spacing, punctuation) is idempotent and is a fixed
point on ``postprocess`` output (S5); non-whitespace characters are conserved
up to the full-width fold (S4); ``postprocess`` equals running the enabled
rules one by one in ``RULE_ORDER`` (S4); the output does not depend on the
input block order (S4); ``finalize`` is idempotent (S5). ``PostprocessOptions``
has no law: it is a validated value object.

Decision D1: there is no ``replacements`` rule in M1, so it is absent from
``RULE_ORDER`` and from the option fields. The composition oracle below uses
only the public functions of the other post-processing modules plus a
test-side finalize; it never calls ``pipeline`` internals.
Matrix: tests-20261025-183000.md, section WI-6 (+ rev 1 L8).
"""

import dataclasses
import itertools
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from snapocr.engines.types import OcrResult
from snapocr.postprocess import PostprocessOptions, RULE_ORDER, postprocess
from snapocr.postprocess.layout import build_lines
from snapocr.postprocess.paragraphs import lines_to_text, merge_paragraphs
from snapocr.postprocess.pipeline import finalize
from snapocr.postprocess.punctuation import to_fullwidth_punctuation
from snapocr.postprocess.spacing import add_cjk_latin_spacing
from support.pp_strategies import arbitrary_layouts, grid_layouts, mixed_text, rect

DOC = Path(__file__).resolve().parents[2] / "docs" / "postprocess.md"
SWITCHES = list(itertools.product([True, False], repeat=3))
_FOLD = str.maketrans("，；：？！。", ",;:?!.")

F1_EXPECTED = "使用 Python3 截图识别，自动复制到剪贴板。\nHello World, snapocr 123 test."


def _nonws(s: str) -> str:
    return "".join(c for c in s if not c.isspace())


def _fold(s: str) -> str:
    return s.translate(_FOLD)


def _opts(paragraphs: bool, spacing: bool, punctuation: bool) -> PostprocessOptions:
    return PostprocessOptions(paragraphs=paragraphs, spacing=spacing, punctuation=punctuation)


def _text_chain(s: str, spacing: bool, punctuation: bool) -> str:
    if spacing:
        s = add_cjk_latin_spacing(s)
    if punctuation:
        s = to_fullwidth_punctuation(s)
    return s


def _finalize_oracle(s: str) -> str:
    return "\n".join(line.rstrip() for line in s.split("\n")).strip("\n")


def _oracle(result: OcrResult, paragraphs: bool, spacing: bool, punctuation: bool) -> str:
    lines = build_lines(result)
    if lines:
        region = (min(line.left for line in lines), max(line.right for line in lines))
        if paragraphs:
            lines = merge_paragraphs(lines, region=region)
    text = lines_to_text(lines)
    return _finalize_oracle(_text_chain(text, spacing, punctuation))


# --- S1 / S2 examples ---------------------------------------------------------


def test_f1_full_chain():
    result = OcrResult(
        (
            rect("Hello World, snapocr 123 test.", 24, 112, 470, 150),
            rect("自动复制到剪贴板。", 436, 31, 720, 67),
            rect("使用Python3截图识别，", 24, 30, 430, 68),
        )
    )
    assert postprocess(result) == F1_EXPECTED
    assert postprocess(result, None) == F1_EXPECTED
    assert postprocess(result, PostprocessOptions()) == F1_EXPECTED


_SWITCH_LAYOUT = OcrResult(
    (
        rect("按下快捷键启动snapocr", 0, 0, 400, 20),  # full line (region 0..400)
        rect("截图识别,结果进入剪贴板。", 0, 30, 300, 50),
        rect("完成", 0, 100, 40, 120),  # gap 50 = 2.5h
    )
)


@pytest.mark.parametrize(
    ("paragraphs", "spacing", "punctuation", "expected"),
    [
        (True, True, True, "按下快捷键启动 snapocr 截图识别，结果进入剪贴板。\n\n完成"),
        (True, True, False, "按下快捷键启动 snapocr 截图识别,结果进入剪贴板。\n\n完成"),
        (True, False, True, "按下快捷键启动snapocr截图识别，结果进入剪贴板。\n\n完成"),
        (True, False, False, "按下快捷键启动snapocr截图识别,结果进入剪贴板。\n\n完成"),
        (False, True, True, "按下快捷键启动 snapocr\n截图识别，结果进入剪贴板。\n\n完成"),
        (False, True, False, "按下快捷键启动 snapocr\n截图识别,结果进入剪贴板。\n\n完成"),
        (False, False, True, "按下快捷键启动snapocr\n截图识别，结果进入剪贴板。\n\n完成"),
        (False, False, False, "按下快捷键启动snapocr\n截图识别,结果进入剪贴板。\n\n完成"),
    ],
)
def test_switch_matrix(paragraphs, spacing, punctuation, expected):
    assert postprocess(_SWITCH_LAYOUT, _opts(paragraphs, spacing, punctuation)) == expected


@pytest.mark.parametrize(("paragraphs", "spacing", "punctuation"), SWITCHES)
def test_empty_for_every_switch_subset(paragraphs, spacing, punctuation):
    options = _opts(paragraphs, spacing, punctuation)
    assert postprocess(OcrResult(()), options) == ""
    blank = OcrResult((rect("  \t", 0, 0, 10, 10), rect("\n", 0, 40, 10, 50)))
    assert postprocess(blank, options) == ""


def test_rule_order_literal_and_options_fields():
    assert RULE_ORDER == ("layout", "paragraphs", "spacing", "punctuation", "finalize")
    assert [f.name for f in dataclasses.fields(PostprocessOptions)] == ["paragraphs", "spacing", "punctuation"]
    default = PostprocessOptions()
    assert (default.paragraphs, default.spacing, default.punctuation) == (True, True, True)


def test_docs_list_rules_in_order():
    assert DOC.is_file(), f"missing {DOC}"
    text = DOC.read_text(encoding="utf-8")
    positions = []
    for name in RULE_ORDER:
        token = f"`{name}`"
        assert token in text, f"{token} not documented"
        positions.append(text.index(token))
    assert len(positions) == 5
    assert positions == sorted(positions)
    assert len(set(positions)) == len(positions)


def test_option_and_input_guards():
    for kwargs, field in (({"paragraphs": 1}, "paragraphs"), ({"spacing": "yes"}, "spacing"), ({"punctuation": None}, "punctuation")):
        with pytest.raises(ValueError, match=field):
            PostprocessOptions(**kwargs)
    block = rect("中文", 0, 0, 10, 10)
    for bad in ("text", None, [block]):
        with pytest.raises(TypeError):
            postprocess(bad)
    with pytest.raises(TypeError):
        postprocess(OcrResult((block,)), options={"spacing": False})
    options = PostprocessOptions()
    with pytest.raises(dataclasses.FrozenInstanceError):
        options.spacing = False  # type: ignore[misc]


def test_finalize_guard_non_str():
    for bad in (None, 1, ["a"]):
        with pytest.raises(TypeError):
            finalize(bad)  # type: ignore[arg-type]


def test_finalize_examples_and_idempotence():
    assert finalize("\n\na \n\n\nb\t\n\n") == "a\n\n\nb"
    assert finalize("  a\n b") == "  a\n b"  # rev 1 L8: leading whitespace is kept
    assert finalize("") == ""
    assert finalize(" \n\t\n") == ""


@given(st.text(alphabet="ab中 \t\n", max_size=30))
def test_finalize_properties(s):
    out = finalize(s)
    assert finalize(out) == out
    assert not out.startswith("\n") and not out.endswith("\n")
    assert all(line == line.rstrip() for line in out.split("\n"))
    assert _nonws(out) == _nonws(s)


# --- S4 / S5 properties -------------------------------------------------------

_switch = st.booleans()


@settings(deadline=None)
@given(grid_layouts(), _switch, _switch, _switch)
def test_equals_sequential_composition(layout, paragraphs, spacing, punctuation):
    blocks, _ = layout
    result = OcrResult(blocks)
    assert postprocess(result, _opts(paragraphs, spacing, punctuation)) == _oracle(result, paragraphs, spacing, punctuation)


@given(mixed_text(40), _switch, _switch)
def test_text_chain_idempotent_on_text(s, spacing, punctuation):
    once = _text_chain(s, spacing, punctuation)
    assert _text_chain(once, spacing, punctuation) == once


@settings(deadline=None)
@given(grid_layouts(), _switch, _switch, _switch)
def test_text_chain_idempotent(layout, paragraphs, spacing, punctuation):
    blocks, _ = layout
    out = postprocess(OcrResult(blocks), _opts(paragraphs, spacing, punctuation))
    assert out != "" or not blocks
    assert _text_chain(out, spacing, punctuation) == out


@settings(deadline=None)
@given(grid_layouts(), _switch, _switch, _switch)
def test_fold_conservation_vs_generated_rows(layout, paragraphs, spacing, punctuation):
    blocks, expected = layout
    out = postprocess(OcrResult(blocks), _opts(paragraphs, spacing, punctuation))
    assert _fold(_nonws(out)) == _fold(_nonws("".join(text for text, _ in expected)))


@settings(deadline=None)
@given(arbitrary_layouts(), st.randoms(use_true_random=False), _switch, _switch, _switch)
def test_shuffle_invariance(blocks, rnd, paragraphs, spacing, punctuation):
    options = _opts(paragraphs, spacing, punctuation)
    shuffled = list(blocks)
    rnd.shuffle(shuffled)
    assert postprocess(OcrResult(tuple(shuffled)), options) == postprocess(OcrResult(blocks), options)
