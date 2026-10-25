"""F2 WI-1: snapocr.postprocess.chars -- character classifiers (unit lane).

Law: is_cjk, is_cjk_punct and is_latin_alnum are pairwise disjoint and each
equals its code-point definition (full oracle, Q6 / M5). No conservation or
round-trip law -- they are table lookups.
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from snapocr.postprocess.chars import is_cjk, is_cjk_punct, is_latin_alnum

CLASSIFIERS = [is_cjk, is_cjk_punct, is_latin_alnum]


@pytest.mark.parametrize(
    ("c", "expected"),
    [(c, True) for c in ["一", "鿿", "㐀", "䶿", "中"]]
    + [
        (c, False)
        for c in ["䷀", "㏿", "ꀀ", "\U00020000", "　", "，", "a", "あ", "가", "０"]
    ],
)
def test_is_cjk_range_edges(c, expected):
    assert is_cjk(c) is expected


@pytest.mark.parametrize(
    ("c", "expected"),
    [(c, True) for c in "，。！？：；、「」（）《》…—“”‘’【】［～･〿"]
    + [(c, False) for c in [",", ".", "!", "?", "　", "Ａ", "０", "中", "·", "぀", "ｦ"]],
)
def test_is_cjk_punct_members(c, expected):
    assert is_cjk_punct(c) is expected


@pytest.mark.parametrize(
    ("c", "expected"),
    [(c, True) for c in "azAZ09"] + [(c, False) for c in ["é", "０", "Ａ", "_", "-", " ", "中"]],
)
def test_is_latin_alnum_ascii_only(c, expected):
    assert is_latin_alnum(c) is expected


def _cjk_def(c: str) -> bool:
    o = ord(c)
    return 0x3400 <= o <= 0x4DBF or 0x4E00 <= o <= 0x9FFF


def _cjk_punct_def(c: str) -> bool:
    o = ord(c)
    return (
        0x3001 <= o <= 0x303F
        or 0xFF01 <= o <= 0xFF0F
        or 0xFF1A <= o <= 0xFF20
        or 0xFF3B <= o <= 0xFF40
        or 0xFF5B <= o <= 0xFF65
        or c in "“”‘’…—"
    )


@given(
    st.one_of(
        st.characters(),
        st.characters(min_codepoint=0x3000, max_codepoint=0xA000),
        st.characters(min_codepoint=0xFF00, max_codepoint=0xFF65),
    )
)
def test_classifiers_match_definition_and_are_disjoint(c):
    assert is_latin_alnum(c) == (c.isascii() and c.isalnum())
    assert is_cjk(c) == _cjk_def(c)
    assert is_cjk_punct(c) == _cjk_punct_def(c)
    assert sum(f(c) for f in CLASSIFIERS) <= 1


@pytest.mark.parametrize("fn", CLASSIFIERS, ids=lambda f: f.__name__)
def test_classifier_guards(fn):
    for bad in ["", "ab"]:
        with pytest.raises(ValueError):
            fn(bad)
    for bad in [None, 65]:
        with pytest.raises(TypeError):
            fn(bad)
