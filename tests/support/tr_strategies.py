"""Hypothesis strategies for F4 translator tests (matrix §1)."""

from __future__ import annotations

import string

from hypothesis import strategies as st

MARKER_PREFIX = "ZQXJ"


def marker() -> st.SearchStrategy[str]:
    """Unique privacy marker: ASCII, never present in messages, hints, templates or fixtures."""
    return st.text("0123456789abcdef", min_size=8, max_size=12).map(lambda s: MARKER_PREFIX + s)


# --- base_url candidates (WI-2) ---------------------------------------------

_SCHEMES = ["http", "https", "HTTP", "ftp", ""]
_SEPARATORS = ["://", ":/", ""]
_USERINFO = ["", "user@", "127.0.0.1:11434@"]
_HOSTS = [
    "127.0.0.1",
    "localhost",
    "[::1]",
    "127.0.0.2",
    "0.0.0.0",
    "127.1",
    "2130706433",
    "0x7f.0.0.1",
    "[::ffff:127.0.0.1]",
    "127.0.0.1.evil.com",
    "evil.com",
    "",
]
_PORTS = ["", ":", ":011434", ":+1", ":١٢٣", ":１１４３４"]
_PATHS = ["", "/", "//", "/v1", "/v1/", "/x", "?a=1", "#f", "%2f"]
_TAILS = ["", "\n", " "]


def url_candidates() -> st.SearchStrategy[str]:
    structured = st.builds(
        lambda *parts: "".join(parts),
        st.sampled_from(_SCHEMES),
        st.sampled_from(_SEPARATORS),
        st.sampled_from(_USERINFO),
        st.sampled_from(_HOSTS) | st.text(max_size=15),
        st.sampled_from(_PORTS) | st.integers(-1, 70000).map(lambda p: f":{p}"),
        st.sampled_from(_PATHS),
        st.sampled_from(_TAILS),
    )
    return st.one_of(structured, st.text())


def ok_base_url() -> st.SearchStrategy[tuple[str, int]]:
    """(url, port) pairs that must be accepted."""
    return st.builds(
        lambda p, slash: (f"http://127.0.0.1:{p}{slash}", p),
        st.integers(1, 65535),
        st.sampled_from(["", "/"]),
    )


# --- sampling (WI-2 / WI-4) ---------------------------------------------------

_finite = {"allow_nan": False, "allow_infinity": False}

_SAMPLING_VALUES = {
    "temperature": st.floats(0, 2, **_finite) | st.integers(0, 2),
    "top_p": st.floats(0, 1, **_finite) | st.integers(0, 1),
    "presence_penalty": st.floats(-2, 2, **_finite),
    "frequency_penalty": st.floats(-2, 2, **_finite),
    "max_tokens": st.integers(1, 100_000),
    "seed": st.integers(-(2**31), 2**31),
    "stop": st.text(max_size=5) | st.lists(st.text(max_size=5), max_size=3),
}


def sampling_dicts() -> st.SearchStrategy[dict]:
    return st.fixed_dictionaries({}, optional=_SAMPLING_VALUES)


# --- scripts (WI-3 / WI-7) ----------------------------------------------------

cjk = st.characters(min_codepoint=0x4E00, max_codepoint=0x9FFF)
latin = st.sampled_from(string.ascii_letters)
_ASCII_PUNCT_NO_ANGLE = [c for c in string.punctuation if c not in "<>"]
neutral = st.one_of(
    st.sampled_from(string.digits),
    st.sampled_from(_ASCII_PUNCT_NO_ANGLE),
    st.sampled_from(" \t\n"),
    st.characters(min_codepoint=0xFF21, max_codepoint=0xFF3A),
    st.characters(min_codepoint=0xFF41, max_codepoint=0xFF5A),
    st.characters(min_codepoint=0xFF10, max_codepoint=0xFF19),
    st.sampled_from(["，", "。", "、", "「", "」", "😀", "あ", "가", "𠀀", "é", "　"]),
)


def script_text(max_size: int = 60) -> st.SearchStrategy[str]:
    return st.lists(st.one_of(cjk, latin, neutral), max_size=max_size).map("".join)
