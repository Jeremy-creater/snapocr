"""Qt lane plugin: unit runs are offscreen, gui tests fail without --qt-desktop (CLAUDE.md)."""

from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent

PLATFORM_TEST = """
import os
from PySide6.QtGui import QGuiApplication

def test_platform(qapp):
    print("ENV=" + repr(os.environ.get("QT_QPA_PLATFORM")))
    print("PLATFORM=" + QGuiApplication.platformName())
"""

ENV_ONLY_TEST = """
import os

def test_env():
    print("ENV=" + repr(os.environ.get("QT_QPA_PLATFORM")))
"""

GUI_TEST = """
import pytest

@pytest.mark.gui
def test_needs_desktop():
    pass
"""


@pytest.fixture
def lane(pytester, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", str(TESTS))
    pytester.makeconftest('pytest_plugins = ["support.qt_lane"]')
    return pytester


@pytest.mark.parametrize("preset", [None, "windows", "minimal"])
def test_unit_runs_force_offscreen(lane, monkeypatch, preset):
    if preset is None:
        monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
    else:
        monkeypatch.setenv("QT_QPA_PLATFORM", preset)
    lane.makepyfile(PLATFORM_TEST)
    result = lane.runpytest_subprocess("-s")
    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(["*ENV='offscreen'*", "*PLATFORM=offscreen*"])


def test_qt_desktop_leaves_platform_alone(lane, monkeypatch):
    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
    lane.makepyfile(ENV_ONLY_TEST)
    result = lane.runpytest_subprocess("-s", "--qt-desktop")
    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(["*ENV=None*"])


def test_gui_test_fails_without_qt_desktop(lane):
    lane.makepyfile(GUI_TEST)
    result = lane.runpytest_subprocess()
    result.assert_outcomes(errors=1)
    assert result.ret != 0
    result.stdout.fnmatch_lines(["*-m gui --qt-desktop*"])
    assert "skipped" not in result.stdout.str()


def test_gui_test_runs_with_qt_desktop(lane):
    lane.makepyfile(GUI_TEST)
    result = lane.runpytest_subprocess("--qt-desktop")
    result.assert_outcomes(passed=1)
