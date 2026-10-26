"""F4 WI-3: translation direction (F4-1, D1, matrix Q15)."""

import math
import string

import pytest
from hypothesis import given
from hypothesis import strategies as st

from snapocr.postprocess.chars import is_cjk
from snapocr.translators.config import TranslatorConfig
from snapocr.translators.direction import count_scripts, detect_target_lang, resolve_target
from support.tr_strategies import cjk, latin, neutral, script_text

thresholds = st.floats(min_value=0, max_value=1, exclude_min=True)


def test_count_scripts_examples():
    assert count_scripts("使用 Python3 截图") == (4, 6)
    assert count_scripts("") == (0, 0)
    assert count_scripts("Ａｂ１２。、あ가𠀀é") == (0, 0)
    assert count_scripts("abcXYZ") == (0, 6)
    assert count_scripts("中a") == (1, 1)


@given(script_text(), script_text())
def test_count_scripts_additive_and_oracle(a, b):
    ca, la = count_scripts(a)
    cb, lb = count_scripts(b)
    assert count_scripts(a + b) == (ca + cb, la + lb)
    assert count_scripts(a) == (sum(map(is_cjk, a)), sum(c in string.ascii_letters for c in a))


def test_detect_examples():
    assert detect_target_lang("今天天气很好", 0.3) == "en"
    assert detect_target_lang("Hello world", 0.3) == "zh"
    assert detect_target_lang("使用 Python3 截图", 0.3) == "en"
    assert detect_target_lang("使用 Python3 截图", 0.5) == "zh"


def test_detect_float_boundaries():
    assert detect_target_lang("中" * 3 + "a" * 7, 0.3) == "en"
    assert detect_target_lang("中" * 3 + "a" * 8, 0.3) == "zh"
    assert detect_target_lang("中" * 7 + "a" * 3, 0.7) == "en"
    assert detect_target_lang("中" + "a" * 9, 0.1) == "en"
    assert detect_target_lang("中", 1.0) == "en"
    assert detect_target_lang("中a", 1.0) == "zh"
    assert detect_target_lang("a", 0.3) == "zh"


@pytest.mark.parametrize("text", ["", "12345", "!!!", "--", " \n\t", "１２３", "😀", "Ａ"])
def test_detect_no_letters_is_none(text):
    assert detect_target_lang(text, 0.3) is None


def test_detect_guards():
    for bad_text in [None, b"ab"]:
        with pytest.raises(TypeError):
            detect_target_lang(bad_text, 0.3)  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            count_scripts(bad_text)  # type: ignore[arg-type]
    for bad_t in [0, 1.5, math.nan, True]:
        with pytest.raises(ValueError):
            detect_target_lang("中a", bad_t)


@given(st.text() | script_text(), thresholds)
def test_detect_total_and_matches_prd_expression(s, t):
    got = detect_target_lang(s, t)
    c, l = count_scripts(s)
    assert got in {"en", "zh", None}
    if c + l == 0:
        assert got is None
    else:
        assert got == ("en" if c / (c + l) >= t else "zh")


@given(script_text(), st.lists(st.tuples(st.integers(0, 60), neutral)), thresholds)
def test_neutral_insertion_invariant(s, inserts, t):
    chars = list(s)
    for pos, ch in inserts:
        chars.insert(min(pos, len(chars)), ch)
    assert detect_target_lang("".join(chars), t) == detect_target_lang(s, t)


@given(script_text(), st.lists(st.integers(0, 60), min_size=1, max_size=10), st.data(), thresholds)
def test_monotone_in_scripts(s, positions, data, t):
    before = detect_target_lang(s, t)
    if before not in ("en", "zh"):
        return
    alphabet = cjk if before == "en" else latin
    chars = list(s)
    for pos in positions:
        chars.insert(min(pos, len(chars)), data.draw(alphabet))
    assert detect_target_lang("".join(chars), t) == before


@given(script_text(), thresholds, thresholds)
def test_threshold_monotone(s, a, b):
    t1, t2 = min(a, b), max(a, b)
    if detect_target_lang(s, t2) == "en":
        assert detect_target_lang(s, t1) == "en"
    if detect_target_lang(s, t1) == "zh":
        assert detect_target_lang(s, t2) == "zh"


@given(st.sampled_from(["zh", "en"]), st.text())
def test_resolve_target_fixed_ignores_text(lang, text):
    assert resolve_target(text, TranslatorConfig(target_lang=lang)) == lang


def test_resolve_target_fixed_examples():
    zh = TranslatorConfig(target_lang="zh")
    assert resolve_target("Hello", zh) == "zh"
    assert resolve_target("你好", zh) == "zh"
    assert resolve_target("12345", TranslatorConfig(target_lang="en")) == "en"


def test_resolve_target_auto_uses_config_threshold():
    assert resolve_target("使用 Python3 截图", TranslatorConfig(direction_threshold=0.3)) == "en"
    assert resolve_target("使用 Python3 截图", TranslatorConfig(direction_threshold=0.5)) == "zh"
    assert resolve_target("12345", TranslatorConfig()) is None
