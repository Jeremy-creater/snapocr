"""WI-9: the test-side CER gate ``support.cer_check.assert_cer_within`` (unit lane).

No law: this is a threshold check over examples; its edges are pinned here.
"""

import pytest

from support.cer_check import assert_cer_within

REF = "甲" * 100


def _substitute(s: str, positions, ch: str = "乙") -> str:
    chars = list(s)
    for p in positions:
        chars[p] = ch
    return "".join(chars)


def test_exactly_at_limit_passes_closed_interval():
    hyp = _substitute(REF, [10, 50])
    assert assert_cer_within(hyp, REF, 0.02, "two-subs") == 0.02


def test_identical_returns_zero():
    assert assert_cer_within(REF, REF, 0.02) == 0.0


def test_three_substitutions_fail_with_cer_and_first_position():
    hyp = _substitute(REF, [10, 50, 90])
    with pytest.raises(AssertionError) as info:
        assert_cer_within(hyp, REF, 0.02, "three-subs")
    msg = str(info.value)
    assert "three-subs" in msg
    assert "0.0300" in msg
    assert "index 10" in msg
    # context around the first difference, from both sides
    assert "甲甲甲甲甲乙甲甲甲甲" in msg
    assert "甲甲甲甲甲甲甲甲甲甲" in msg


def test_empty_hyp_is_assertion_error_with_cer_one():
    with pytest.raises(AssertionError) as info:
        assert_cer_within("", REF, 0.02, "empty-hyp")
    assert type(info.value) is AssertionError
    assert not isinstance(info.value, ValueError)
    msg = str(info.value)
    assert "1.0000" in msg
    assert "index 0" in msg


def test_trailing_insertions_fail_at_position_100():
    hyp = REF + "乙" * 3
    with pytest.raises(AssertionError) as info:
        assert_cer_within(hyp, REF, 0.02, "tail-insert")
    msg = str(info.value)
    assert "0.0300" in msg
    assert "index 100" in msg


def test_whitespace_is_normalized_on_both_sides():
    ref = "甲乙 丙丁\n戊己\t庚辛"
    hyp = "甲乙丙丁戊己庚辛"
    assert assert_cer_within(hyp, ref, 0.0) == 0.0
    assert assert_cer_within("甲 乙\n丙丁戊己庚辛", ref.replace(" ", ""), 0.0) == 0.0


def test_difference_index_is_in_normalized_text():
    # The space in hyp is removed before comparing, so the first difference
    # is at normalized index 2, not raw index 3.
    with pytest.raises(AssertionError) as info:
        assert_cer_within("甲乙 X丁", "甲乙丙丁", 0.0)
    assert "index 2" in str(info.value)
    assert "0.2500" in str(info.value)


@pytest.mark.parametrize("ref", ["", "  \n\t"])
@pytest.mark.parametrize("hyp", ["", "甲"])
def test_empty_reference_is_a_setup_error(hyp, ref):
    # An empty reference would make the gate pass vacuously (or be undefined),
    # so it is rejected as a broken fixture, not reported as an OCR result.
    with pytest.raises(ValueError, match="reference is empty"):
        assert_cer_within(hyp, ref, 0.02)
