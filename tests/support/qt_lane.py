"""pytest plugin: Qt platform per lane (CLAUDE.md "GUI 测试方式").

Without ``--qt-desktop`` every run is offscreen, even if the environment asks
for another platform, so the unit lane never touches the real desktop. Tests
marked ``gui`` need the real desktop and FAIL (never skip) without the option.
"""

import os
import sys

import pytest

GUI_COMMAND = "python -m pytest -m gui --qt-desktop"


def pytest_addoption(parser):
    parser.addoption(
        "--qt-desktop",
        action="store_true",
        default=False,
        help="use the real Windows desktop for Qt (gui lane); default is offscreen",
    )


def pytest_configure(config):
    # Runs before pytest-qt creates the QApplication (that happens in the qapp fixture).
    if not config.getoption("--qt-desktop"):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"


def pytest_runtest_setup(item):
    if item.get_closest_marker("gui") and not item.config.getoption("--qt-desktop"):
        pytest.fail(
            f"gui tests need the real desktop; run them with: {GUI_COMMAND}",
            pytrace=False,
        )


def pytest_sessionfinish(session):
    # Offscreen Qt segfaults while destroying the application if the clipboard
    # still holds a QMimeData set from Python (WI-13, R7). Clear it so a green
    # run exits 0. Never on the real desktop: that is Jeremy's clipboard.
    if session.config.getoption("--qt-desktop") or "PySide6.QtGui" not in sys.modules:
        return
    from PySide6.QtGui import QGuiApplication

    if QGuiApplication.instance() is not None:
        QGuiApplication.clipboard().clear()
