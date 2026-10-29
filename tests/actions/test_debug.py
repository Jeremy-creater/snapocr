"""M3 WI-12: debug mode files (PRD F12-1, F12-3; M3 plan D16).

Pinned here:
- ``DEBUG_DIR`` is ``debug`` under the runtime data directory (PRD F12-1, F21-2).
- ``debug_stem(now, job_id)`` is ``YYYYMMDD-HHMMSS-fff-<job id>`` in local time.
- ``debug_text(record)`` has the sections "## OCR 原文", "## 后处理文本", then
  "## 译文" and "## 错误" only when present; UTF-8, LF line ends.
- ``DebugDump(directory, clock)(job_id, record)`` creates the directory when
  needed and writes ``<stem>.png`` (the record's PNG bytes) and ``<stem>.txt``.
  An ``OSError`` is logged as one WARNING naming only the exception type; it
  never propagates.
"""

import datetime
import logging
from pathlib import Path

import pytest

from snapocr.actions.debug import DEBUG_DIR, DebugDump, debug_stem, debug_text
from snapocr.actions.outcomes import RunRecord

PNG = b"\x89PNG\r\n\x1a\nfake"
NOW = datetime.datetime(2026, 10, 27, 9, 5, 7, 42_999)
MARK = "⟦M7⟧"


def fixed(now=NOW):
    return lambda: now


def test_debug_dir_is_under_the_runtime_dir():
    from snapocr.app import DEFAULT_LOG_DIR

    assert DEBUG_DIR == DEFAULT_LOG_DIR / "debug"


def test_stem():
    assert debug_stem(NOW, 12) == "20261027-090507-042-12"
    assert debug_stem(datetime.datetime(2026, 1, 2, 23, 59, 59, 999_999), 1) == "20260102-235959-999-1"


def test_text_ocr_only():
    record = RunRecord(PNG, "原文 0CR", "原文 OCR")
    assert debug_text(record) == "## OCR 原文\n原文 0CR\n\n## 后处理文本\n原文 OCR\n"


def test_text_with_translation_and_error():
    record = RunRecord(PNG, "a", "b", translation="c", error="d")
    assert debug_text(record) == "## OCR 原文\na\n\n## 后处理文本\nb\n\n## 译文\nc\n\n## 错误\nd\n"


def test_text_error_without_translation():
    record = RunRecord(PNG, "", "", error="failed to load OCR engine")
    assert debug_text(record) == "## OCR 原文\n\n\n## 后处理文本\n\n\n## 错误\nfailed to load OCR engine\n"


def test_dump_writes_png_and_text(tmp_path):
    directory = tmp_path / "runtime" / "debug"
    record = RunRecord(PNG, "raw" + MARK, "text", translation="译文")
    DebugDump(directory, fixed())(7, record)
    assert sorted(p.name for p in directory.iterdir()) == ["20261027-090507-042-7.png", "20261027-090507-042-7.txt"]
    assert (directory / "20261027-090507-042-7.png").read_bytes() == PNG
    assert (directory / "20261027-090507-042-7.txt").read_bytes() == debug_text(record).encode("utf-8")


def test_same_moment_different_jobs_do_not_overwrite(tmp_path):
    dump = DebugDump(tmp_path, fixed())
    dump(1, RunRecord(PNG, "a", "a"))
    dump(2, RunRecord(b"other", "b", "b"))
    assert len(list(tmp_path.iterdir())) == 4
    assert (tmp_path / "20261027-090507-042-1.png").read_bytes() == PNG


def test_write_failure_is_logged_by_type_only(tmp_path, caplog):
    blocker = tmp_path / "debug"
    blocker.write_text("a file where the directory should be", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="snapocr.actions.debug"):
        DebugDump(blocker, fixed())(3, RunRecord(PNG, MARK, MARK, error=MARK))
    records = [r for r in caplog.records if r.name == "snapocr.actions.debug"]
    assert len(records) == 1 and records[0].levelno == logging.WARNING
    message = records[0].getMessage()
    assert message == "debug files not written: FileExistsError"  # mkdir over an existing file
    assert records[0].exc_info is None
