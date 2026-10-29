"""M2 WI-22: start-up arguments, logging and the uncaught-exception hook (plan D12; CLAUDE.md privacy).

Pinned here:
- ``parse_args(args)``: ``--config PATH`` (default: ``default_config_path()``, PRD F21-1);
  anything else is a usage error (``SystemExit(2)``).
- ``setup_logging(log_dir)`` adds one WARNING-level file handler to the root
  logger writing ``log_dir/snapocr.log``; the directory is created on the
  first record, not before. Calling it again replaces the earlier handler.
- ``safe_traceback(exc)`` names the exception type and each frame
  (file:line in function) but never the message or source lines.
- ``install_excepthook()`` logs uncaught exceptions that way at CRITICAL.
- Privacy: a whole OCR job run (success, empty, engine failure, crash) logs
  nothing that contains the OCR text.
- ``python -m snapocr`` runs ``launch.main()`` and exits with its code.
"""

import logging
import os
import runpy
import sys
import threading
from pathlib import Path

import pytest

from snapocr.actions.flows import FlowDeps
from snapocr.actions.runner import JobRunner, ocr_job
from snapocr.app import (
    DEFAULT_LOG_DIR,
    LOG_FILE_NAME,
    install_excepthook,
    parse_args,
    runtime_issues,
    safe_traceback,
    setup_logging,
)
from snapocr.config.files import default_config_path
from snapocr.engines.errors import EngineLoadError
from snapocr.engines.types import OcrResult
from snapocr.paths import runtime_dir
from snapocr.postprocess import PostprocessOptions, Replacements
from support.fake_actions import holder_for
from support.pp_strategies import rect

MARKER = "snapocr-private-marker-7f3a"


# --- arguments ---------------------------------------------------------------------


def test_default_config_path():
    assert parse_args([]).config == default_config_path()


def test_config_option(tmp_path):
    path = tmp_path / "mine.toml"
    assert parse_args(["--config", str(path)]).config == path


@pytest.mark.parametrize("args", [["--bogus"], ["extra"], ["--config"]])
def test_bad_arguments_are_usage_errors(args, capsys):
    with pytest.raises(SystemExit) as info:
        parse_args(args)
    assert info.value.code == 2


def test_default_log_dir_is_the_runtime_dir_of_this_environment():
    """F21-2: read once at import from the real environment (Jeremy's machine sets SNAPOCR_RUNTIME_DIR)."""
    assert DEFAULT_LOG_DIR == runtime_dir(os.environ, home=Path.home())[0]
    assert LOG_FILE_NAME == "snapocr.log"


def test_runtime_issues_name_a_relative_variable(monkeypatch, tmp_path):
    monkeypatch.setenv("SNAPOCR_RUNTIME_DIR", "logs")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    default = tmp_path / "snapocr"
    assert [str(i) for i in runtime_issues()] == [
        f"SNAPOCR_RUNTIME_DIR: 不是绝对路径（logs），日志和 debug 文件改放 {default}"
    ]


def test_no_runtime_issues_for_an_absolute_variable_or_none(monkeypatch, tmp_path):
    monkeypatch.setenv("SNAPOCR_RUNTIME_DIR", str(tmp_path))
    assert runtime_issues() == []
    monkeypatch.delenv("SNAPOCR_RUNTIME_DIR")
    assert runtime_issues() == []


# --- logging ---------------------------------------------------------------------------


@pytest.fixture
def root_logging():
    root = logging.getLogger()
    before, level = list(root.handlers), root.level
    yield root
    for h in root.handlers:
        if h not in before:
            root.removeHandler(h)
            h.close()
    root.setLevel(level)


def test_log_dir_is_created_on_first_warning_only(tmp_path, root_logging):
    log_dir = tmp_path / "runtime" / "snapocr"
    setup_logging(log_dir)
    logging.getLogger("snapocr.test").info("not written")
    assert not log_dir.exists()
    logging.getLogger("snapocr.test").warning("written %d", 42)
    text = (log_dir / LOG_FILE_NAME).read_text(encoding="utf-8")
    assert "written 42" in text and "WARNING" in text and "snapocr.test" in text
    assert "not written" not in text


def test_setup_logging_twice_keeps_one_handler(tmp_path, root_logging):
    setup_logging(tmp_path / "a")
    setup_logging(tmp_path / "b")
    logging.getLogger("snapocr.test").error("once")
    assert not (tmp_path / "a" / LOG_FILE_NAME).exists()
    assert (tmp_path / "b" / LOG_FILE_NAME).read_text(encoding="utf-8").count("once") == 1


def _raise_with_marker():
    raise ValueError(f"text was {MARKER}")


def test_safe_traceback_names_type_and_frames_only():
    try:
        _raise_with_marker()
    except ValueError as exc:
        text = safe_traceback(exc)
    assert text.startswith("ValueError\n")
    assert "_raise_with_marker" in text and "test_app.py" in text
    assert MARKER not in text


def test_excepthook_logs_without_the_message(tmp_path, root_logging, monkeypatch):
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    setup_logging(tmp_path)
    install_excepthook()
    try:
        _raise_with_marker()
    except ValueError as exc:
        sys.excepthook(type(exc), exc, exc.__traceback__)
    text = (tmp_path / LOG_FILE_NAME).read_text(encoding="utf-8")
    assert "CRITICAL" in text and "uncaught exception" in text and "ValueError" in text
    assert "_raise_with_marker" in text
    assert MARKER not in text


def test_excepthook_passes_keyboard_interrupt_on(monkeypatch, tmp_path, root_logging):
    seen = []
    monkeypatch.setattr(sys, "excepthook", lambda *a: seen.append(a[0]))
    setup_logging(tmp_path)
    install_excepthook()
    sys.excepthook(KeyboardInterrupt, KeyboardInterrupt(), None)
    assert seen == [KeyboardInterrupt]
    assert not (tmp_path / LOG_FILE_NAME).exists()


# --- privacy of a whole OCR run --------------------------------------------------------


def test_ocr_jobs_never_log_the_ocr_text(caplog):
    result = OcrResult((rect(f"识别 {MARKER}", 0, 0, 200, 20),))
    deps_ok = FlowDeps(holder_for(result), PostprocessOptions(), Replacements.from_mapping({}))
    deps_fail = FlowDeps(holder_for(result, load_error=EngineLoadError(model_paths=(), hint="h", detail="d")),
                         PostprocessOptions(), Replacements.from_mapping({}))
    deps_crash = FlowDeps(holder_for(RuntimeError(MARKER)), PostprocessOptions(), Replacements.from_mapping({}))
    done = threading.Event()
    events = []

    def on_event(e):
        events.append(e)
        if len(events) == 3:
            done.set()

    with caplog.at_level(logging.DEBUG):
        runner = JobRunner(on_event)
        try:
            for d in (deps_ok, deps_fail, deps_crash):
                runner.submit(ocr_job(b"png", d))
            assert done.wait(10)
        finally:
            runner.shutdown()
    assert events[0].outcome.clipboard.text.endswith(MARKER)  # the text really went through
    assert MARKER not in caplog.text


# --- python -m snapocr -------------------------------------------------------------------


def test_python_m_snapocr_runs_launch_main(monkeypatch):
    import snapocr.gui.platform.launch as launch

    monkeypatch.setattr(launch, "main", lambda argv=None: 7)
    with pytest.raises(SystemExit) as info:
        runpy.run_module("snapocr", run_name="__main__")
    assert info.value.code == 7


def test_importing_snapocr_main_does_not_run_it():
    import importlib

    module = importlib.import_module("snapocr.__main__")
    assert callable(module.main)
