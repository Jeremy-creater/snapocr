"""Debug mode: each OCR / translate result saved as files (PRD F12; M3 plan D16). No Qt.

Only used when ``[debug] enabled = true``. The directory is fixed under the
runtime data directory (CLAUDE.md: full OCR text only there, only in debug
mode). Old files are never deleted. A write failure is logged by exception
type only and never reaches the job.
"""

from __future__ import annotations

import datetime
import logging
from collections.abc import Callable
from pathlib import Path

from snapocr.actions.outcomes import HistoryRecord
from snapocr.app import DEFAULT_LOG_DIR

DEBUG_DIR = DEFAULT_LOG_DIR / "debug"
_log = logging.getLogger(__name__)


def debug_stem(now: datetime.datetime, job_id: int) -> str:
    """``YYYYMMDD-HHMMSS-fff-<job id>``: sorts by time, unique per job (F12-1)."""
    return f"{now:%Y%m%d-%H%M%S}-{now.microsecond // 1000:03d}-{job_id}"


def debug_text(record: HistoryRecord) -> str:
    parts = [f"## OCR 原文\n{record.raw}\n", f"## 后处理文本\n{record.text}\n"]
    if record.translation is not None:
        parts.append(f"## 译文\n{record.translation}\n")
    if record.error is not None:
        parts.append(f"## 错误\n{record.error}\n")
    return "\n".join(parts)


class DebugDump:
    """``on_record`` hook of ``JobRunner``: writes ``<stem>.png`` and ``<stem>.txt`` into ``directory``."""

    def __init__(self, directory: Path, clock: Callable[[], datetime.datetime] = datetime.datetime.now) -> None:
        self._directory = directory
        self._clock = clock

    def __call__(self, job_id: int, record: HistoryRecord) -> None:
        stem = debug_stem(self._clock(), job_id)
        try:
            self._directory.mkdir(parents=True, exist_ok=True)
            (self._directory / f"{stem}.png").write_bytes(record.png)
            (self._directory / f"{stem}.txt").write_bytes(debug_text(record).encode("utf-8"))
        except OSError as err:
            # F12-3: the type only; the message may hold the path or worse.
            _log.warning("debug files not written: %s", type(err).__name__)
