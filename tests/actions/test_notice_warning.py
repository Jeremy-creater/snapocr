"""M5 WI-3: failure notices carry the warning icon (PRD F18-3; M5 plan D5).

Pinned here:
- ``Notice`` has a keyword field ``warning`` (default ``False``, must be a bool).
- Failure notices are built with ``warning=True``: capture failed, OCR
  failed, engine load failed, save failed, hotkey registration failed,
  config issues, config file could not be opened, job crashed.
- All other notices keep ``warning=False``; titles and bodies do not change.
- The tray icon for each: ``tests/gui/test_notice_icon.py``.
"""

from pathlib import Path

import pytest

from snapocr.actions import messages as m
from snapocr.actions.flows import capture_flow
from snapocr.actions.outcomes import Notice
from snapocr.commands import Command
from snapocr.config.schema import ConfigIssue
from snapocr.engines.errors import EngineLoadError, EngineRuntimeError
from snapocr.hotkeys import HotkeyFailure

CFG = Path("D:/x/config.local.toml")
LOG = Path("D:/x/snapocr.log")

FAILURES = {
    "capture": lambda: m.capture_failed_notice("BitBlt failed"),
    "ocr": lambda: m.ocr_failed_notice(EngineRuntimeError("engine crashed")),
    "engine": lambda: m.engine_failed_notice(EngineLoadError(["D:/m/det.onnx"], "h"), LOG),
    "save": lambda: m.save_failed_notice(Path("D:/shots/a.png"), "Permission denied"),
    "hotkey": lambda: m.hotkey_failed_notice([HotkeyFailure(Command.OCR, "Alt+2", 1409)]),
    "config": lambda: m.config_issues_notice([ConfigIssue(CFG, "hotkeys.ocr", "bad")]),
    "open-config": lambda: m.open_config_failed_notice(CFG, "no app"),
    "crash": lambda: m.job_crashed_notice("RuntimeError"),
}

OTHERS = {
    "ocr-ok": lambda: m.ocr_ok_notice("你好"),
    "ocr-count": lambda: m.ocr_ok_notice("你好", show_text=False),
    "code-ok": lambda: m.code_ok_notice("x = 1"),
    "table-ok": lambda: m.table_ok_notice(2, 3),
    "empty": m.ocr_empty_notice,
    "settings-saved": m.settings_saved_notice,
    "config-opened": m.config_opened_notice,
    "debug-on": lambda: m.debug_on_notice(Path("D:/x/debug")),
    "copied": lambda: capture_flow(b"png").notice,
}


def test_notice_is_not_a_warning_by_default():
    assert Notice("a", "b").warning is False
    assert Notice("a", "b", warning=True).warning is True


def test_warning_must_be_a_bool():
    with pytest.raises(TypeError, match="warning"):
        Notice("a", "b", warning=1)


@pytest.mark.parametrize("name", sorted(FAILURES))
def test_failure_notices_are_warnings(name):
    assert FAILURES[name]().warning is True


@pytest.mark.parametrize("name", sorted(OTHERS))
def test_other_notices_are_not(name):
    assert OTHERS[name]().warning is False


@pytest.mark.parametrize("name", sorted(FAILURES))
def test_title_and_body_do_not_change(name):
    n = FAILURES[name]()
    assert n == Notice(n.title, n.body, warning=True)

