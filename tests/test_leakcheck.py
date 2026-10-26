"""Positive controls for the F4 privacy helpers (matrix S6, S9)."""

import json

import pytest
from hypothesis import given

from support.leakcheck import no_leak
from support.tr_strategies import marker

SECRET = "ZQXJ0123456789ab"


class _WithAttr(Exception):
    pass


def _raise_with_context(inner: BaseException) -> BaseException:
    try:
        try:
            raise inner
        except BaseException:
            raise RuntimeError("clean outer")  # noqa: B904 - implicit __context__ on purpose
    except RuntimeError as outer:
        return outer


def _raise_with_cause(inner: BaseException) -> BaseException:
    try:
        raise RuntimeError("clean outer") from inner
    except RuntimeError as outer:
        return outer


def _json_error() -> json.JSONDecodeError:
    try:
        json.loads('{"x": "' + SECRET)
    except json.JSONDecodeError as e:
        return e
    raise AssertionError("unreachable")


def _unicode_error() -> UnicodeDecodeError:
    try:
        (b"\xff" + SECRET.encode()).decode("utf-8")
    except UnicodeDecodeError as e:
        return e
    raise AssertionError("unreachable")


def test_no_leak_positive_control():
    with pytest.raises(AssertionError):
        no_leak(ValueError(SECRET), SECRET)
    with pytest.raises(AssertionError):
        no_leak(_raise_with_context(_json_error()), SECRET)
    with pytest.raises(AssertionError):
        no_leak(_raise_with_cause(_unicode_error()), SECRET)
    e = _WithAttr("clean")
    e.payload = SECRET
    with pytest.raises(AssertionError):
        no_leak(e, SECRET)
    no_leak(_raise_with_context(ValueError("clean inner")), SECRET)


def test_no_leak_message_does_not_echo_secret():
    with pytest.raises(AssertionError) as info:
        no_leak(ValueError(SECRET), SECRET)
    assert SECRET not in str(info.value)


@given(marker())
def test_marker_strategy_shape(m):
    assert m.startswith("ZQXJ")
    assert 12 <= len(m) <= 16
    assert m.isascii()
