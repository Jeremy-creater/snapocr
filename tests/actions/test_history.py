"""M2 WI-10: last-results store (PRD F10-3, F10-4 data layer; plan D7).

Pinned here:
- ``snapshot()`` is newest first and holds at most ``capacity`` records.
- The default capacity is 10 (D7, a constant, not a config key).
- ``capacity`` must be a positive int; 0, negatives and bools raise.
- Records are stored as given (identity), never copied or written to disk.
"""

import ast
import threading
from pathlib import Path

import pytest
from hypothesis import settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, initialize, invariant, rule

from snapocr.actions.history import ResultHistory
from snapocr.actions.outcomes import HistoryRecord

HISTORY_SRC = Path(__file__).resolve().parents[2] / "src" / "snapocr" / "actions" / "history.py"


def rec(i: int) -> HistoryRecord:
    return HistoryRecord(png=b"png%d" % i, raw=f"raw{i}", text=f"text{i}")


def test_push_twelve_keeps_latest_ten_newest_first():
    history = ResultHistory()
    for i in range(12):
        history.push(rec(i))
    assert history.snapshot() == tuple(rec(i) for i in range(11, 1, -1))


def test_empty_snapshot_is_empty_tuple():
    assert ResultHistory().snapshot() == ()


def test_snapshot_is_a_tuple_detached_from_later_pushes():
    history = ResultHistory(3)
    history.push(rec(0))
    before = history.snapshot()
    history.push(rec(1))
    assert type(before) is tuple
    assert before == (rec(0),)
    assert history.snapshot() == (rec(1), rec(0))


def test_records_are_stored_by_identity():
    history = ResultHistory(2)
    record = rec(7)
    history.push(record)
    assert history.snapshot()[0] is record


def test_capacity_one_keeps_only_the_latest():
    history = ResultHistory(1)
    for i in range(5):
        history.push(rec(i))
    assert history.snapshot() == (rec(4),)


def test_capacity_ten_fills_exactly():
    history = ResultHistory(10)
    for i in range(10):
        history.push(rec(i))
    assert history.snapshot() == tuple(rec(i) for i in range(9, -1, -1))
    history.push(rec(10))
    assert history.snapshot() == tuple(rec(i) for i in range(10, 0, -1))


@pytest.mark.parametrize("capacity", [0, -1, -10])
def test_non_positive_capacity_is_rejected(capacity):
    with pytest.raises(ValueError, match="capacity"):
        ResultHistory(capacity)


@pytest.mark.parametrize("capacity", [True, 2.0, "10", None])
def test_non_int_capacity_is_rejected(capacity):
    with pytest.raises(TypeError, match="capacity"):
        ResultHistory(capacity)


class HistoryMachine(RuleBasedStateMachine):
    """Reference model: a plain list; the store is its sliding window, reversed."""

    @initialize(capacity=st.integers(min_value=1, max_value=12))
    def setup(self, capacity):
        self.capacity = capacity
        self.history = ResultHistory(capacity)
        self.model: list[HistoryRecord] = []
        self.counter = 0

    @rule()
    def push(self):
        record = rec(self.counter)
        self.counter += 1
        self.history.push(record)
        self.model.append(record)

    @rule(i=st.integers(min_value=0, max_value=3))
    def push_duplicate_value(self, i):
        record = rec(i)  # equal records may repeat; the store keeps both
        self.history.push(record)
        self.model.append(record)

    @invariant()
    def matches_model(self):
        assert self.history.snapshot() == tuple(reversed(self.model[-self.capacity:]))


HistoryMachine.TestCase.settings = settings(max_examples=60, stateful_step_count=30, deadline=None)
TestHistoryMachine = HistoryMachine.TestCase


def test_concurrent_pushes_neither_lose_nor_duplicate():
    threads_n, per_thread, capacity = 4, 250, 10
    history = ResultHistory(capacity)
    start = threading.Barrier(threads_n)
    seen_lengths: list[int] = []

    def worker(t):
        start.wait()
        for i in range(per_thread):
            history.push(HistoryRecord(png=b"", raw=f"{t}", text=f"{t}-{i}"))
            seen_lengths.append(len(history.snapshot()))

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(threads_n)]
    for th in threads:
        th.start()
    for th in threads:
        th.join(timeout=10)
    assert not any(th.is_alive() for th in threads)

    snap = history.snapshot()
    texts = [r.text for r in snap]
    assert len(snap) == capacity
    assert len(set(texts)) == capacity
    assert max(seen_lengths) == capacity
    # Within one thread, later pushes appear earlier in the snapshot.
    for t in range(threads_n):
        mine = [int(x.split("-")[1]) for x in texts if x.startswith(f"{t}-")]
        assert mine == sorted(mine, reverse=True)
    # The newest record overall is some thread's last push.
    assert texts[0] in {f"{t}-{per_thread - 1}" for t in range(threads_n)}


def test_concurrent_snapshot_never_exceeds_capacity_or_tears():
    history = ResultHistory(5)
    stop = threading.Event()
    bad: list[tuple] = []

    def reader():
        while not stop.is_set():
            snap = history.snapshot()
            nums = [int(r.text[4:]) for r in snap]
            if len(snap) > 5 or nums != sorted(nums, reverse=True) or len(set(nums)) != len(nums):
                bad.append(tuple(nums))

    th = threading.Thread(target=reader)
    th.start()
    try:
        for i in range(3000):
            history.push(rec(i))
    finally:
        stop.set()
        th.join(timeout=10)
    assert bad == []
    assert history.snapshot() == tuple(rec(i) for i in range(2999, 2994, -1))


FORBIDDEN_MODULES = {"pathlib", "tempfile", "pickle", "shelve", "sqlite3", "io", "os", "shutil", "json", "marshal"}


def test_history_module_never_touches_disk():
    tree = ast.parse(HISTORY_SRC.read_text(encoding="utf-8"))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert roots & FORBIDDEN_MODULES == set()
    assert "open" not in names
    assert "__import__" not in names
