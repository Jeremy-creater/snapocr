"""pytest plugin: tests for one platform only (M9 plan D7, CLAUDE.md "平台标记").

Windows-only files and folders are not collected on a Mac and the other way
round; tests marked ``windows`` / ``macos`` are deselected on the other
platform. Nothing is skipped. The terminal summary says what was left out.
A test marked both, or an unknown platform, is a usage error.
"""

from __future__ import annotations

import sys
from pathlib import PurePosixPath

import pytest

# Paths relative to the rootdir, written with "/".
EXCLUSIVE_PATHS = {
    "win32": ("tests/platform/windows", "tests/perf/test_gui_latency.py"),
    "darwin": ("tests/platform/macos",),
}
MARKERS = {"win32": "windows", "darwin": "macos"}
OTHER = {"win32": "darwin", "darwin": "win32"}


class MarkedForBoth(ValueError):
    def __init__(self, item: object) -> None:
        super().__init__(f"{item!r} is marked both windows and macos")
        self.item = item


def _check(platform: str) -> None:
    if platform not in MARKERS:
        raise ValueError(f"unknown platform {platform!r}; tests run on 'win32' or 'darwin'")


def platform_exclusion(relpath: str, platform: str) -> str | None:
    """The other platform's path that ``relpath`` lies in, or None when it belongs here."""
    _check(platform)
    parts = PurePosixPath(relpath).parts
    for prefix in EXCLUSIVE_PATHS[OTHER[platform]]:
        own = PurePosixPath(prefix).parts
        if parts[: len(own)] == own:
            return prefix
    return None


def select(items, platform):
    """Split ``(item, marker names)`` pairs into ``(kept, deselected)``, in input order."""
    _check(platform)
    other = MARKERS[OTHER[platform]]
    kept, deselected = [], []
    for item, markers in items:
        if {"windows", "macos"} <= set(markers):
            raise MarkedForBoth(item)
        (deselected if other in markers else kept).append(item)
    return kept, deselected


# --- hooks -------------------------------------------------------------------------------

_left_out: dict[str, object] = {"paths": set(), "deselected": 0}


def pytest_configure(config):
    try:
        _check(sys.platform)
    except ValueError as exc:
        raise pytest.UsageError(str(exc)) from None
    _left_out["paths"] = set()
    _left_out["deselected"] = 0


def pytest_ignore_collect(collection_path, config):
    try:
        relpath = collection_path.relative_to(config.rootpath).as_posix()
    except ValueError:
        return None
    prefix = platform_exclusion(relpath, sys.platform)
    if prefix is None:
        return None
    _left_out["paths"].add(prefix)
    return True


def pytest_collection_modifyitems(config, items):
    pairs = [(item, {m.name for m in item.iter_markers()}) for item in items]
    try:
        kept, deselected = select(pairs, sys.platform)
    except MarkedForBoth as exc:
        raise pytest.UsageError(f"{exc.item.nodeid} is marked both windows and macos") from None
    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = kept
    _left_out["deselected"] = len(deselected)


def pytest_terminal_summary(terminalreporter):
    paths = ", ".join(sorted(_left_out["paths"])) or "none"
    terminalreporter.write_line(
        f"platform lanes: {sys.platform}; not collected: {paths}; "
        f"deselected (marked {MARKERS[OTHER[sys.platform]]}): {_left_out['deselected']}"
    )
