"""F4 WI-1: TranslationResult and the Translator protocol."""

from dataclasses import FrozenInstanceError

import pytest
from hypothesis import given
from hypothesis import strategies as st

from snapocr.translators.types import TranslationResult, Translator


def test_result_fields_and_equality():
    r = TranslationResult("Hello", "en", False)
    assert (r.text, r.target_lang, r.skipped) == ("Hello", "en", False)
    same = TranslationResult("Hello", "en", False)
    assert r == same
    assert hash(r) == hash(same)
    assert r != TranslationResult("Hello", "zh", False)


def test_result_frozen():
    r = TranslationResult("Hello", "en", False)
    with pytest.raises(FrozenInstanceError):
        r.text = "x"  # type: ignore[misc]


@pytest.mark.parametrize("lang", ["fr", "EN", "", "auto"])
def test_result_rejects_bad_target_lang(lang):
    with pytest.raises(ValueError):
        TranslationResult("x", lang, False)  # type: ignore[arg-type]


@pytest.mark.parametrize("text", [b"x", None])
def test_result_rejects_non_str_text(text):
    with pytest.raises(TypeError):
        TranslationResult(text, "en", False)  # type: ignore[arg-type]


@pytest.mark.parametrize("skipped", [1, None])
def test_result_rejects_non_bool_skipped(skipped):
    with pytest.raises(TypeError):
        TranslationResult("x", "en", skipped)  # type: ignore[arg-type]


@pytest.mark.parametrize("args", [("x", "en", True), ("x", None, False)])
def test_result_rejects_inconsistent_skipped(args):
    with pytest.raises(ValueError):
        TranslationResult(*args)


@given(st.text(), st.sampled_from(["zh", "en", None]), st.booleans())
def test_result_skipped_iff_no_target(text, lang, skipped):
    if skipped == (lang is None):
        r = TranslationResult(text, lang, skipped)
        assert (r.text, r.target_lang, r.skipped) == (text, lang, skipped)
    else:
        with pytest.raises(ValueError):
            TranslationResult(text, lang, skipped)


def test_translator_protocol_runtime_checkable():
    class Echo:
        def translate(self, text):
            return TranslationResult(text, None, True)

    assert isinstance(Echo(), Translator)
    assert not isinstance(object(), Translator)
