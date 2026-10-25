"""WI-12: the download guard on fake classes (unit lane).

Law (S5): after the guard exits -- normally, by exception or by
KeyboardInterrupt -- the replaced attribute is identical (``is``) to its
original raw value, and an inherited attribute leaves no own entry behind.
Paired real path: ``tests/engines/test_no_download_real.py``.
"""

from dataclasses import dataclass

import pytest
from hypothesis import given
from hypothesis import strategies as st

from snapocr.engines.errors import EngineLoadError
from snapocr.engines.offline import DownloadBlockedError, block_downloads

_MISSING = object()


@dataclass
class FakeInput:
    file_url: str


def _make_downloader():
    """A fresh fake shaped like rapidocr's ``DownloadFile`` (classmethod ``run``)."""

    class FakeDownloader:
        saved: list = []

        @classmethod
        def run(cls, input_params):
            cls.saved.append(input_params.file_url)
            return "downloaded"

    return FakeDownloader


def test_download_inside_guard_raises_and_nothing_is_saved():
    fake = _make_downloader()

    with block_downloads(fake):
        with pytest.raises(DownloadBlockedError) as info:
            fake.run(FakeInput("https://example.invalid/keys.txt"))
        with pytest.raises(DownloadBlockedError):
            fake().run(FakeInput("https://example.invalid/other.txt"))

    assert fake.saved == []
    err = info.value
    assert isinstance(err, EngineLoadError)
    assert err.model_paths == ()
    assert "https://example.invalid/keys.txt" in str(err)
    assert "offline" in str(err)


def test_original_restored_after_normal_exit():
    fake = _make_downloader()
    original = vars(fake)["run"]

    with block_downloads(fake):
        assert vars(fake)["run"] is not original

    assert vars(fake)["run"] is original
    assert fake.run(FakeInput("u")) == "downloaded"
    assert fake.saved == ["u"]


@pytest.mark.parametrize("exc_type", [ValueError, DownloadBlockedError, KeyboardInterrupt])
def test_original_restored_and_exception_propagates(exc_type):
    fake = _make_downloader()
    original = vars(fake)["run"]

    def body():
        with block_downloads(fake):
            if exc_type is DownloadBlockedError:
                fake.run(FakeInput("u"))
            raise exc_type("boom")

    with pytest.raises(exc_type):
        body()

    assert vars(fake)["run"] is original
    assert fake.saved == []


def test_inherited_attribute_is_blocked_then_removed_again():
    parent = _make_downloader()

    class Child(parent):
        pass

    assert "run" not in vars(Child)

    with block_downloads(Child):
        with pytest.raises(DownloadBlockedError):
            Child.run(FakeInput("u"))
        assert parent.run(FakeInput("p")) == "downloaded"

    assert "run" not in vars(Child)
    assert Child.run(FakeInput("c")) == "downloaded"
    assert parent.saved == ["p", "c"]


def test_guard_error_names_input_without_file_url():
    fake = _make_downloader()

    with block_downloads(fake), pytest.raises(DownloadBlockedError) as info:
        fake.run("plain-arg")

    assert "plain-arg" in str(info.value)


_attr_values = st.one_of(
    st.integers(),
    st.text(max_size=5),
    st.just(None),
    st.builds(lambda: classmethod(lambda cls: 1)),
    st.builds(lambda: staticmethod(lambda: 2)),
    st.builds(lambda: (lambda self: 3)),
)


@given(
    name=st.from_regex(r"[a-z][a-z0-9_]{0,10}", fullmatch=True),
    value=st.one_of(st.just(_MISSING), _attr_values),
    raises=st.booleans(),
)
def test_property_round_trip_restores_exact_attribute(name, value, raises):
    owner = type("Owner", (), {} if value is _MISSING else {name: value})
    before = dict(vars(owner))

    try:
        with block_downloads(owner, name):
            with pytest.raises(DownloadBlockedError):
                getattr(owner, name)("x")
            if raises:
                raise RuntimeError("body failed")
    except RuntimeError:
        assert raises

    after = dict(vars(owner))
    assert after.keys() == before.keys()
    for key in before:
        assert after[key] is before[key]
