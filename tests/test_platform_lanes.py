"""M9 WI-1 (plan D7): tests for one platform only are left out on the other one.

Pinned here (beyond the plan text):
- Platform-exclusive paths are relative to the rootdir, written with "/":
  ``tests/platform/windows``, ``tests/perf/test_gui_latency.py`` (Windows) and
  ``tests/platform/macos`` (Mac). A path is inside one when the path parts
  start with its parts, so ``tests/platform/windows_x`` is not inside.
- ``select`` keeps the input order and returns ``(kept, deselected)``.
- The terminal summary line is
  ``platform lanes: <platform>; not collected: <paths or none>; deselected (marked <marker>): <n>``.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from support.platform_lanes import MarkedForBoth, platform_exclusion, select

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent

WINDOWS_ONLY = ("tests/platform/windows", "tests/perf/test_gui_latency.py")
MACOS_ONLY = ("tests/platform/macos",)
OWN_PATHS = {"win32": WINDOWS_ONLY, "darwin": MACOS_ONLY}
OTHER = {"win32": "darwin", "darwin": "win32"}
MARKER = {"win32": "windows", "darwin": "macos"}
BAD_PLATFORMS = ["linux", "", "Win32", "DARWIN", "cygwin", "windows", "macos"]


# --- platform_exclusion ------------------------------------------------------------------


@pytest.mark.parametrize("platform", ["win32", "darwin"])
@pytest.mark.parametrize(
    "relpath",
    [
        "tests/test_app.py",
        "tests/config/test_settings.py",
        "tests/platform",
        "tests/platform/windows_x/test_a.py",
        "tests/platform/macosx/test_a.py",
        "tests/perf",
        "tests/perf/test_latency.py",
        "tests/perf/test_gui_latency.pyc",
        "tests/support/win_input.py",
        "platform/windows/test_a.py",
    ],
)
def test_shared_paths_are_kept_on_both_platforms(relpath, platform):
    assert platform_exclusion(relpath, platform) is None


@pytest.mark.parametrize(
    "relpath, expected",
    [
        ("tests/platform/windows", "tests/platform/windows"),
        ("tests/platform/windows/test_launch.py", "tests/platform/windows"),
        ("tests/platform/windows/sub/test_x.py", "tests/platform/windows"),
        ("tests/platform/windows/conftest.py", "tests/platform/windows"),
        ("tests/perf/test_gui_latency.py", "tests/perf/test_gui_latency.py"),
    ],
)
def test_windows_paths_are_left_out_on_mac_only(relpath, expected):
    assert platform_exclusion(relpath, "darwin") == expected
    assert platform_exclusion(relpath, "win32") is None


@pytest.mark.parametrize(
    "relpath",
    ["tests/platform/macos", "tests/platform/macos/test_mac_capture.py", "tests/platform/macos/a/b.py"],
)
def test_mac_paths_are_left_out_on_windows_only(relpath):
    assert platform_exclusion(relpath, "win32") == "tests/platform/macos"
    assert platform_exclusion(relpath, "darwin") is None


@pytest.mark.parametrize("platform", BAD_PLATFORMS)
def test_exclusion_unknown_platform_raises(platform):
    with pytest.raises(ValueError, match="platform"):
        platform_exclusion("tests/test_app.py", platform)


_part = st.text(alphabet="abcdefghijklmnopqrstuvwxyz_0123456789.", min_size=1, max_size=8).filter(
    lambda s: s not in (".", "..")
)


@given(st.sampled_from(["win32", "darwin"]), st.data())
def test_exclusive_paths_are_left_out_only_on_the_other_platform(platform, data):
    """Law: anything under one platform's paths is excluded on the other one and never on its own."""
    prefix = data.draw(st.sampled_from(OWN_PATHS[platform]))
    tail = data.draw(st.lists(_part, max_size=3))
    relpath = "/".join([prefix, *tail])
    assert platform_exclusion(relpath, platform) is None
    assert platform_exclusion(relpath, OTHER[platform]) == prefix


@given(st.lists(_part, min_size=1, max_size=4), st.sampled_from(["win32", "darwin"]))
def test_at_most_one_platform_excludes_a_path(parts, platform):
    """Law: no path is excluded on both platforms (it would run nowhere)."""
    relpath = "/".join(["tests", *parts])
    assert platform_exclusion(relpath, platform) is None or platform_exclusion(relpath, OTHER[platform]) is None


# --- select --------------------------------------------------------------------------------

_markers = st.frozensets(st.sampled_from(["windows", "macos", "gui", "engine", "perf"])).filter(
    lambda m: not {"windows", "macos"} <= m
)


@given(st.lists(_markers, max_size=12), st.sampled_from(["win32", "darwin"]))
def test_select_partitions_the_items(marker_sets, platform):
    """Law: kept and deselected never overlap, together they are every item, each in input order."""
    items = list(enumerate(marker_sets))
    kept, deselected = select(items, platform)
    assert set(kept).isdisjoint(deselected)
    assert sorted(kept + deselected) == list(range(len(items)))
    assert kept == sorted(kept) and deselected == sorted(deselected)


@given(st.lists(_markers, max_size=12), st.sampled_from(["win32", "darwin"]))
def test_select_keeps_unmarked_and_own_marked_and_drops_the_others(marker_sets, platform):
    items = list(enumerate(marker_sets))
    kept, deselected = select(items, platform)
    other = MARKER[OTHER[platform]]
    assert kept == [i for i, m in items if other not in m]
    assert deselected == [i for i, m in items if other in m]


def test_select_examples():
    items = [("plain", set()), ("win", {"windows"}), ("mac", {"macos", "gui"}), ("gui", {"gui"})]
    assert select(items, "win32") == (["plain", "win", "gui"], ["mac"])
    assert select(items, "darwin") == (["plain", "mac", "gui"], ["win"])
    assert select([], "darwin") == ([], [])


@pytest.mark.parametrize("platform", ["win32", "darwin"])
def test_select_both_markers_raises(platform):
    items = [("ok", set()), ("both", {"windows", "macos"})]
    with pytest.raises(MarkedForBoth) as info:
        select(items, platform)
    assert info.value.item == "both"
    assert isinstance(info.value, ValueError)


@pytest.mark.parametrize("platform", BAD_PLATFORMS)
def test_select_unknown_platform_raises(platform):
    with pytest.raises(ValueError, match="platform"):
        select([("plain", set())], platform)


# --- the conftest hooks, end to end (pytester) -------------------------------------------

INI = """
[pytest]
addopts = --strict-markers
markers =
    windows: Windows only
    macos: macOS only
    gui: real desktop
"""

MARKED = """
import pytest

def test_plain():
    pass

@pytest.mark.windows
def test_windows_only():
    pass

@pytest.mark.macos
def test_macos_only():
    pass
"""

# Importing a module that does not exist: collecting this file at all is an error.
NEVER_COLLECTED = """
import snapocr_no_such_module

def test_never():
    pass
"""

OWN_DIR = {"win32": "windows", "darwin": "macos"}


@pytest.fixture
def lanes(pytester, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", str(TESTS))
    pytester.makeini(INI)
    pytester.makeconftest('pytest_plugins = ["support.platform_lanes"]')
    return pytester


def _write(pytester, relpath, source):
    path = pytester.path / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def test_hooks_run_own_platform_and_leave_out_the_other(lanes):
    host = sys.platform
    other = OTHER[host]
    _write(lanes, "tests/test_marked.py", MARKED)
    _write(lanes, f"tests/platform/{OWN_DIR[host]}/test_own_dir.py", "def test_own_dir():\n    pass\n")
    _write(lanes, f"tests/platform/{OWN_DIR[other]}/test_other_dir.py", NEVER_COLLECTED)
    result = lanes.runpytest_subprocess("-rs", "-rx", "tests")
    result.assert_outcomes(passed=3, deselected=1)
    assert result.ret == 0
    expected = (
        f"platform lanes: {host}; not collected: tests/platform/{OWN_DIR[other]}; "
        f"deselected (marked {MARKER[other]}): 1"
    )
    assert expected in result.stdout.lines
    text = result.stdout.str()
    assert "SKIPPED" not in text and "XFAIL" not in text and "snapocr_no_such_module" not in text


def test_hooks_report_nothing_left_out_when_all_is_shared(lanes):
    _write(lanes, "tests/test_plain.py", "def test_a():\n    pass\n")
    result = lanes.runpytest_subprocess("tests")
    result.assert_outcomes(passed=1)
    assert f"platform lanes: {sys.platform}; not collected: none; deselected (marked {MARKER[OTHER[sys.platform]]}): 0" in (
        result.stdout.lines
    )


def test_hooks_deselected_items_are_reported_with_their_ids(lanes):
    _write(lanes, "tests/test_marked.py", MARKED)
    result = lanes.runpytest_subprocess("--collect-only", "-q", "tests")
    other_test = f"tests/test_marked.py::test_{MARKER[OTHER[sys.platform]]}_only"
    own_test = f"tests/test_marked.py::test_{MARKER[sys.platform]}_only"
    assert own_test in result.stdout.lines
    assert other_test not in result.stdout.lines
    assert result.ret == 0


def test_hooks_both_markers_is_a_usage_error(lanes):
    _write(
        lanes,
        "tests/test_both.py",
        "import pytest\n\n@pytest.mark.windows\n@pytest.mark.macos\ndef test_both():\n    pass\n",
    )
    result = lanes.runpytest_subprocess("tests")
    assert result.ret == pytest.ExitCode.USAGE_ERROR
    assert "tests/test_both.py::test_both" in result.stderr.str()
    assert "both windows and macos" in result.stderr.str()


def test_hooks_both_markers_on_module_and_function_is_a_usage_error(lanes):
    _write(
        lanes,
        "tests/test_both.py",
        "import pytest\n\npytestmark = pytest.mark.macos\n\n@pytest.mark.windows\ndef test_both():\n    pass\n",
    )
    result = lanes.runpytest_subprocess("tests")
    assert result.ret == pytest.ExitCode.USAGE_ERROR
    assert "both windows and macos" in result.stderr.str()


def test_hooks_unknown_platform_is_a_usage_error(lanes):
    lanes.makeconftest('import sys\nsys.platform = "linux"\npytest_plugins = ["support.platform_lanes"]\n')
    _write(lanes, "tests/test_plain.py", "def test_a():\n    pass\n")
    result = lanes.runpytest_subprocess("tests")
    assert result.ret == pytest.ExitCode.USAGE_ERROR
    assert "'linux'" in result.stderr.str()


# --- Windows-only test helpers stay in Windows-only files (AST) --------------------------

WINDOWS_SUPPORT = ("win_clipboard", "win_input", "foreground_holder")


def windows_support_uses(source: str) -> set[str]:
    """The Windows-only helpers ``source`` imports from ``support``, or names as a file."""
    found = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module == "support":
                found |= {a.name for a in node.names if a.name in WINDOWS_SUPPORT}
            elif node.module.startswith("support."):
                found |= {n for n in WINDOWS_SUPPORT if node.module == f"support.{n}"}
        elif isinstance(node, ast.Import):
            found |= {n for a in node.names for n in WINDOWS_SUPPORT if a.name == f"support.{n}"}
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            found |= {n for n in WINDOWS_SUPPORT if node.value == n + ".py"}
    return found


def test_scan_finds_every_spelling():
    """The positive control: each way of using a helper is seen; shared helpers are not."""
    assert windows_support_uses("from support import win_clipboard as wc") == {"win_clipboard"}
    assert windows_support_uses("from support.win_input import press_combo") == {"win_input"}
    assert windows_support_uses("import support.win_input") == {"win_input"}
    assert windows_support_uses('p = TESTS / "support" / "foreground_holder.py"') == {"foreground_holder"}
    assert windows_support_uses("from support import png, qimages\nimport support.qt_input") == set()


def test_windows_helpers_only_in_windows_only_files():
    users = {}
    for path in sorted(TESTS.rglob("*.py")):
        if path.parent == TESTS / "support" and path.stem in WINDOWS_SUPPORT:
            continue  # the helpers themselves
        uses = windows_support_uses(path.read_text(encoding="utf-8"))
        if uses:
            users[path.relative_to(ROOT).as_posix()] = uses
    assert users, "the scan found no user at all; it is not looking at the tests"
    misplaced = sorted(rel for rel in users if platform_exclusion(rel, "darwin") is None)
    assert misplaced == []
