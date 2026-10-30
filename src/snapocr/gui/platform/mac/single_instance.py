"""Single instance via ``fcntl.flock`` on a lock file (PRD F23-8, M9 plan D18).

The lock belongs to the open file, so a second ``acquire`` in the same process
fails too (``lockf`` would not), and the kernel drops it when the process ends,
crash included. The file stays on disk afterwards, which is harmless. Its path
comes from ``snapocr.config.files.lock_path``.
"""

from __future__ import annotations

import fcntl
import os
from pathlib import Path


class InstanceLock:
    def __init__(self, fd: int) -> None:
        self._fd: int | None = fd

    def release(self) -> None:
        if self._fd is not None:
            os.close(self._fd)  # closing the file drops the flock
            self._fd = None


def acquire(lock_file: Path | str) -> InstanceLock | None:
    """The lock on ``lock_file``, or None when another holder (any process) has it."""
    lock_file = Path(lock_file)
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock_file, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return None
    return InstanceLock(fd)
