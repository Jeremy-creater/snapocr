"""F2 WI-1: snapocr.postprocess.spans.protected_spans (unit lane).

Law: the result is a sorted tuple of non-empty, in-bounds, non-overlapping
half-open intervals (0 <= s < e <= len, e_i <= s_{i+1}); a URL inserted into
arbitrary mixed text is always covered by one interval. Rules per Q5.
"""

from string import ascii_letters, digits

import pytest
from hypothesis import given
from hypothesis import strategies as st

from snapocr.postprocess.spans import protected_spans
from support.pp_strategies import cjk, fw_punct, latin, mixed_text


def _single(text: str, fragment: str) -> tuple[tuple[int, int], ...]:
    s = text.index(fragment)
    return ((s, s + len(fragment)),)


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        ("见https://example.com/a?b=1", "https://example.com/a?b=1"),
        ("官网www.example.com。", "www.example.com"),
        ("联系a.b@example.com获取", "a.b@example.com"),
        ("运行`pip install`即可", "`pip install`"),
        ("路径 D:\\LLM\\workspace 下", "D:\\LLM\\workspace"),
    ],
)
def test_each_kind_example(text, fragment):
    spans = protected_spans(text)
    assert spans == _single(text, fragment)
    assert [text[s:e] for s, e in spans] == [fragment]


def test_url_with_hanzi_is_one_span():
    text = "访问https://zh.wikipedia.org/wiki/中文"
    assert protected_spans(text) == ((2, len(text)),)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", ()),
        ("https://a.org 说明", ((0, 13),)),
        ("见https://a.org", ((1, 14),)),
        ("see https://a.org.", ((4, 17),)),
        ("见https://a.org。", ((1, 14),)),
        ("见https://a.org/x后", ((1, 17),)),
        ("https://u@host.com/x", ((0, 20),)),
        ("a`b", ()),
        # M6: backticks never span a line break
        ("x`a\nb`y", ()),
        # L9
        ("见https://a.org, 然后", ((1, 14),)),
        ("(https://a.org)", ((1, 14),)),
        ("`a``b`", ((0, 3), (3, 6))),
    ],
)
def test_span_edges(text, expected):
    assert protected_spans(text) == expected


def test_span_edges_text_slices():
    # Pin the boundaries above to their visible content, so an off-by-one
    # in the literal tuples cannot hide.
    assert "see https://a.org."[4:17] == "https://a.org"
    assert "见https://a.org/x后"[1:17] == "https://a.org/x后"
    assert "https://u@host.com/x"[0:20] == "https://u@host.com/x"


@pytest.mark.parametrize("bad", [None, 1, b"https://a.org", ["a"]])
def test_guard_non_str(bad):
    with pytest.raises(TypeError):
        protected_spans(bad)


@given(
    mixed_text(40, with_fragments=False).filter(
        lambda s: "://" not in s and "www." not in s and not set(s) & set("@`\\")
    )
)
def test_no_trigger_no_span(text):
    assert protected_spans(text) == ()


@given(mixed_text(60))
def test_spans_sorted_disjoint_in_bounds(text):
    spans = protected_spans(text)
    assert type(spans) is tuple
    for span in spans:
        assert type(span) is tuple and len(span) == 2
        assert all(type(x) is int for x in span)
    for s, e in spans:
        assert 0 <= s < e <= len(text)
    for (_, e1), (s2, _) in zip(spans, spans[1:]):
        assert e1 <= s2


_scheme = st.sampled_from(["https://", "http://", "www."])
_host = st.text(alphabet=ascii_letters + digits + ".", min_size=1, max_size=15).filter(
    lambda h: not h.endswith(".")
)
_path = st.one_of(
    st.just(""),
    st.lists(st.one_of(cjk, latin), min_size=1, max_size=10).map(lambda p: "/" + "".join(p)),
)
_url = st.builds(lambda a, b, c: a + b + c, _scheme, _host, _path)
_suffix = st.one_of(
    st.just(""),
    st.builds(
        lambda head, rest: head + rest,
        st.one_of(st.sampled_from([" ", "\n", "\t", "\u3000"]), fw_punct),
        mixed_text(20),
    ),
)


@given(mixed_text(30), _url, _suffix)
def test_inserted_url_always_covered(prefix, url, suffix):
    text = prefix + url + suffix
    i = len(prefix)
    spans = protected_spans(text)
    assert any(s <= i and i + len(url) <= e for s, e in spans), (text, url, spans)
