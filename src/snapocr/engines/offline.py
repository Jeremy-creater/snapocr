"""Offline guard: turn any download attempt into an immediate load failure.

Generic and free of heavy deps so it can be unit-tested on a fake class.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from snapocr.engines.errors import EngineLoadError

_MISSING = object()

OFFLINE_HINT = "snapocr runs offline only and never downloads anything"


class DownloadBlockedError(EngineLoadError):
    """Raised by the guard instead of downloading anything."""


def _guard(*args: object, **kwargs: object) -> None:
    raise DownloadBlockedError((), OFFLINE_HINT, detail=f"blocked download attempt: args={args!r} kwargs={kwargs!r}")


@contextmanager
def block_downloads(owner: type, attr: str = "run") -> Iterator[None]:
    """Replace ``owner.<attr>`` with a guard raising ``DownloadBlockedError``.

    The original raw class attribute is restored on exit, also when the body
    raises (including ``KeyboardInterrupt``, which is never swallowed). An
    attribute that was only inherited leaves no own entry behind.
    """
    original = vars(owner).get(attr, _MISSING)
    setattr(owner, attr, staticmethod(_guard))
    try:
        yield
    finally:
        if original is _MISSING:
            delattr(owner, attr)
        else:
            setattr(owner, attr, original)
