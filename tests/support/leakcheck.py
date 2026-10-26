"""Privacy assertion for F4: a secret must not appear anywhere on an exception chain (Q12)."""

from __future__ import annotations

import traceback


def _chain(err: BaseException) -> list[BaseException]:
    seen: list[BaseException] = []
    todo = [err]
    while todo:
        exc = todo.pop()
        if exc is None or any(exc is s for s in seen):
            continue
        seen.append(exc)
        todo.extend([exc.__cause__, exc.__context__])
    return seen


def no_leak(err: BaseException, *secrets: str) -> None:
    """Fail if any secret appears in str/repr/args/vars of any exception on the chain
    (``__cause__`` and ``__context__``) or in the formatted traceback."""
    views = []
    for i, exc in enumerate(_chain(err)):
        name = f"chain[{i}] {type(exc).__name__}"
        views += [
            (f"{name} str()", lambda e=exc: str(e)),
            (f"{name} repr()", lambda e=exc: repr(e)),
            (f"{name} args", lambda e=exc: repr(e.args)),
            (f"{name} vars()", lambda e=exc: repr(vars(e))),
        ]
    views.append(("format_exception", lambda: "".join(traceback.format_exception(err))))
    for where, render in views:
        text = render()
        for secret in secrets:
            if secret in text:
                raise AssertionError(f"secret leaked via {where}")
