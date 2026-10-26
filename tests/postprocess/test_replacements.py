"""M2 WI-5: F2-6 custom replacement table (PRD F2-6 v0.4, M2 plan D10).

Which key ``ReplacementError.key`` names (the same for any insertion order of
an all-str table):
- a non-str key or value names that entry's key (first in insertion order);
- then, in sorted key order, an empty key or an empty value names that key;
- a key that is a substring of another key names the shorter (contained) key;
- a key/value conflict names the key of the entry that owns the value.
"""

import itertools
from types import MappingProxyType

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from snapocr.engines.types import OcrResult
from snapocr.postprocess import PostprocessOptions, postprocess
from snapocr.postprocess.replacements import ReplacementError, Replacements
from support.pp_strategies import arbitrary_layouts, rect

SWITCHES = list(itertools.product([True, False], repeat=3))


def valid_table(m: dict[str, str]) -> bool:
    """PRD F2-6 constraints, written independently of the module under test."""
    if any(not k or not v for k, v in m.items()):
        return False
    keys = list(m)
    if any(a != b and a in b for a in keys for b in keys):
        return False
    for v in m.values():
        for k in keys:
            if k in v or v in k:
                return False
            if any(k.startswith(v[i:]) for i in range(1, len(v))):
                return False
            if any(k.endswith(v[:i]) for i in range(1, len(v))):
                return False
    return True


# --- examples --------------------------------------------------------------------


def test_prd_example():
    r = Replacements.from_mapping({"0CR": "OCR"})
    assert r.apply("0CR 识别") == "OCR 识别"
    assert r.apply("0CR0CR") == "OCROCR"
    assert r.apply("no match") == "no match"
    assert r.apply("") == ""


def test_literal_not_regex():
    r = Replacements.from_mapping({"a.c": "X", "(": "（"})
    assert r.apply("abc a.c (") == "abc X （"


def test_left_to_right_non_overlapping():
    r = Replacements.from_mapping({"ab": "X", "bc": "Y"})
    assert r.apply("abc") == "Xc"
    assert r.apply("bcab") == "YX"
    assert r.apply("abab") == "XX"


def test_empty_table_is_identity():
    assert Replacements.EMPTY.apply("0CR 识别") == "0CR 识别"
    assert Replacements.from_mapping({}) == Replacements.EMPTY
    assert Replacements.from_mapping(MappingProxyType({"0CR": "OCR"})).apply("0CR") == "OCR"


def test_equal_regardless_of_insertion_order():
    a = Replacements.from_mapping({"ab": "X", "cd": "Y"})
    b = Replacements.from_mapping({"cd": "Y", "ab": "X"})
    assert a == b
    assert hash(a) == hash(b)
    assert a != Replacements.EMPTY


def test_from_mapping_copies_input():
    m = {"0CR": "OCR"}
    r = Replacements.from_mapping(m)
    m["0CR"] = "zzz"
    assert r.apply("0CR") == "OCR"


def test_apply_rejects_non_str():
    with pytest.raises(TypeError):
        Replacements.EMPTY.apply(b"abc")


@pytest.mark.parametrize(
    ("mapping", "key"),
    [
        ({"": "a"}, ""),
        ({"a": ""}, "a"),
        ({"ok": "fine", "a": ""}, "a"),
        ({1: "a"}, 1),
        ({"a": 1}, "a"),
        ({"a": None}, "a"),
        ({"ab": "x", "b": "y"}, "b"),  # key inside another key
        ({"xab": "1", "ab": "2"}, "ab"),
        ({"ab": "abc"}, "ab"),  # key inside a value
        ({"abc": "b"}, "abc"),  # value inside a key
        ({"ab": "xa"}, "ab"),  # suffix "a" of the value starts the key
        ({"ab": "bx"}, "ab"),  # prefix "b" of the value ends the key
        ({"xy": "q", "qz": "w"}, "xy"),  # the D10 counterexample
        ({"ab": "z", "cd": "abq"}, "cd"),  # another entry's key inside this value
        ({"cd": "zab", "ab": "q"}, "cd"),
    ],
)
def test_invalid_tables(mapping, key):
    with pytest.raises(ReplacementError) as info:
        Replacements.from_mapping(mapping)
    assert info.value.key == key
    assert info.value.reason
    assert repr(key) in str(info.value)


@pytest.mark.parametrize("value", [None, [("a", "b")], "ab"])
def test_non_mapping_rejected(value):
    with pytest.raises(ReplacementError) as info:
        Replacements.from_mapping(value)
    assert info.value.key is None


# --- pipeline --------------------------------------------------------------------


def test_postprocess_applies_before_spacing():
    result = OcrResult((rect("0CR识别", 0, 0, 100, 20),))
    assert postprocess(result, None, Replacements.from_mapping({"0CR": "OCR"})) == "OCR 识别"
    assert postprocess(result) == "0CR 识别"


def test_postprocess_replaces_per_block_not_across_blocks():
    table = Replacements.from_mapping({"中文": "汉语"})
    one = OcrResult((rect("中文", 0, 0, 40, 20),))
    two = OcrResult((rect("中", 0, 0, 20, 20), rect("文", 22, 0, 42, 20)))
    assert postprocess(one, None, table) == "汉语"
    assert postprocess(two, None, table) == "中文"


def test_postprocess_rejects_bad_replacements_type():
    with pytest.raises(TypeError):
        postprocess(OcrResult(()), None, {"0CR": "OCR"})


# --- properties ------------------------------------------------------------------

small = st.text(alphabet="abxyz", min_size=0, max_size=3)
tables = st.dictionaries(small, small, max_size=4)


@given(tables)
def test_validation_total_and_matches_oracle(m):
    try:
        Replacements.from_mapping(m)
    except ReplacementError as e:
        assert not valid_table(m)
        assert e.key in m
    else:
        assert valid_table(m)


@settings(suppress_health_check=[HealthCheck.filter_too_much])
@given(tables, st.text(alphabet="abxyz ", max_size=30))
def test_idempotent_and_no_key_left(m, text):
    assume(valid_table(m))
    r = Replacements.from_mapping(m)
    once = r.apply(text)
    assert r.apply(once) == once
    assert not any(k in once for k in m)


@settings(suppress_health_check=[HealthCheck.filter_too_much])
@given(tables, st.text(alphabet="abxyz", max_size=30), st.randoms(use_true_random=False))
def test_insertion_order_irrelevant(m, text, rnd):
    items = list(m.items())
    rnd.shuffle(items)
    shuffled = dict(items)
    try:
        r = Replacements.from_mapping(m)
    except ReplacementError as e:
        with pytest.raises(ReplacementError) as again:
            Replacements.from_mapping(shuffled)
        assert again.value.key == e.key
    else:
        assert Replacements.from_mapping(shuffled).apply(text) == r.apply(text)


@given(arbitrary_layouts(), st.sampled_from(SWITCHES))
def test_empty_table_does_not_change_pipeline(blocks, switches):
    result = OcrResult(blocks)
    options = PostprocessOptions(*switches)
    assert postprocess(result, options, Replacements.EMPTY) == postprocess(result, options)
    assert postprocess(result, options, None) == postprocess(result, options)


@given(st.lists(st.sampled_from(["0CR", "OCR", "0C", "R", " ", "识别", "0"]), max_size=12))
def test_prd_example_matches_str_replace(parts):
    # A single key with no self-overlap behaves exactly like str.replace.
    text = "".join(parts)
    assert Replacements.from_mapping({"0CR": "OCR"}).apply(text) == text.replace("0CR", "OCR")
