"""Shared Hypothesis strategies for the F2 post-processing tests.

Matrix: .claude/tdd-guardian/tests-20261025-183000.md, section "共享生成器"
(``cjk`` uses the revision-1 L10 widened version). Layout / paragraph
generators are added by the work items that need them.
"""

from string import ascii_letters, digits

from hypothesis import strategies as st

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
