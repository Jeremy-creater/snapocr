"""Last results (PRD F10-3): the most recent records, in memory only. Thread-safe.

Plan D7: the capacity is fixed at 10 and is not a config key. Nothing is written
to disk; records are kept as given.
"""

from __future__ import annotations

import threading
from collections import deque

from snapocr.actions.outcomes import HistoryRecord

CAPACITY = 10


class ResultHistory:
    def __init__(self, capacity: int = CAPACITY) -> None:
        if type(capacity) is not int:
            raise TypeError(f"capacity: expected int, got {type(capacity).__name__}")
        if capacity < 1:
            raise ValueError(f"capacity must be at least 1, got {capacity}")
        self._records: deque[HistoryRecord] = deque(maxlen=capacity)
        self._lock = threading.Lock()

    def push(self, record: HistoryRecord) -> None:
        with self._lock:
            self._records.append(record)

    def snapshot(self) -> tuple[HistoryRecord, ...]:
        """Newest first."""
        with self._lock:
            return tuple(reversed(self._records))
