"""Start-up arguments, logging and the uncaught-exception hook (plan D12). No Qt, no ctypes.

Started with pythonw (the ``snapocr`` gui-script), ``sys.stderr`` is None, so
anything not logged is lost. WARNING and above go to ``snapocr.log`` in the
runtime data directory (PRD F21-2), whose directory is created on the first
record. Logs never contain OCR text: exceptions are
logged by type and frame locations only, never by message.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import traceback
from pathlib import Path

from snapocr.config.files import default_config_path
from snapocr.config.schema import ConfigIssue
from snapocr.paths import RUNTIME_ENV, runtime_dir

DEFAULT_LOG_DIR = runtime_dir(os.environ, home=Path.home())[0]  # read once, at import (F21-2)
LOG_FILE_NAME = "snapocr.log"
_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_log = logging.getLogger("snapocr")


def parse_args(args: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="snapocr", description="Tray screenshot, OCR and translation tool.")
    parser.add_argument("--config", type=Path, default=default_config_path(), help="config file (default: %(default)s)")
    return parser.parse_args(args)


class _LazyFileHandler(logging.FileHandler):
    """A FileHandler that creates its directory when the first record is written."""

    def __init__(self, path: Path) -> None:
        super().__init__(path, encoding="utf-8", delay=True)

    def _open(self):  # noqa: ANN202 - logging.FileHandler hook
        Path(self.baseFilename).parent.mkdir(parents=True, exist_ok=True)
        return super()._open()


_handler: logging.Handler | None = None


def setup_logging(log_dir: Path = DEFAULT_LOG_DIR) -> None:
    """Send WARNING and above to ``log_dir/snapocr.log``; replaces an earlier call's handler."""
    global _handler
    root = logging.getLogger()
    if _handler is not None:
        root.removeHandler(_handler)
        _handler.close()
    _handler = _LazyFileHandler(log_dir / LOG_FILE_NAME)
    _handler.setLevel(logging.WARNING)
    _handler.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(_handler)  # the root logger's default level is already WARNING


def safe_traceback(exc: BaseException) -> str:
    """The exception type, then one ``file:line in function`` per frame; no message, no source."""
    frames = traceback.extract_tb(exc.__traceback__)
    return type(exc).__name__ + "\n" + "".join(f"  {f.filename}:{f.lineno} in {f.name}\n" for f in frames)


def install_excepthook() -> None:
    """Log uncaught exceptions (also those raised in Qt slots) instead of losing them."""
    previous = sys.excepthook

    def hook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            previous(exc_type, exc, tb)
            return
        _log.critical("uncaught exception: %s", safe_traceback(exc.with_traceback(tb)))

    sys.excepthook = hook


def runtime_issues() -> list[ConfigIssue]:
    """F21-2: a refused ``SNAPOCR_RUNTIME_DIR``, for the start-up notice (F9-3)."""
    problem = runtime_dir(os.environ, home=Path.home())[1]
    return [ConfigIssue(Path(RUNTIME_ENV), "", problem)] if problem else []
