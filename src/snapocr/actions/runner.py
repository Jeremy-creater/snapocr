"""FIFO job runner with two workers (PRD F8-2, F7-5, F7-6, F18-1; plan D2, M5 plan D3). No Qt.

A job is a callable returning an iterable (usually a generator) of flow
results. Each result becomes an event tagged with the job id and is handed to
``on_event`` on a worker thread; the GUI bridge moves it to the GUI thread.

Recognition runs on "snapocr-jobs", one job at a time. When a job yields an
``OcrStage`` (a translate job), the rest of the same iterator, the model
request, moves to "snapocr-translate", so a translation waiting for the model
never holds up the next OCR (F18-1). Model requests also run one at a time.
Whatever a job does after its ``OcrStage`` runs on the translate worker, so
it must not use the OCR engine.
Every job ends with exactly one terminal event (``OcrDone``, ``TranslateDone``,
``WarmedUp`` or ``JobCrashed``). A terminal result's history record is pushed
before its event is delivered.

The worker is a daemon thread, so a translation stuck in its socket timeout
never holds up interpreter exit (D2: no ``ThreadPoolExecutor``).
"""

from __future__ import annotations

import logging
import math
import queue
import threading
import time
import traceback
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass

from snapocr.actions.flows import (
    FlowDeps,
    code_ocr_flow,
    ocr_flow,
    table_ocr_flow,
    translate_ocr_stage,
    translate_stage,
)
from snapocr.actions.history import ResultHistory
from snapocr.actions.outcomes import HistoryRecord, OcrStage, Outcome, TranslateOutcome
from snapocr.engines.errors import EngineLoadError
from snapocr.engines.holder import EngineHolder
from snapocr.translators.types import Translator

_log = logging.getLogger(__name__)

Job = Callable[[], Iterable[object]]

THREAD_NAME = "snapocr-jobs"
TRANSLATE_THREAD_NAME = "snapocr-translate"


class IncompleteJobError(RuntimeError):
    """A job ended without a terminal result."""


@dataclass(frozen=True)
class OcrDone:
    job_id: int
    outcome: Outcome


@dataclass(frozen=True)
class TranslateStarted:
    """OCR finished; the popup shows ``stage.text`` while translation runs."""

    job_id: int
    stage: OcrStage


@dataclass(frozen=True)
class TranslateDone:
    job_id: int
    outcome: TranslateOutcome


@dataclass(frozen=True)
class WarmedUp:
    job_id: int
    ok: bool


@dataclass(frozen=True)
class JobCrashed:
    job_id: int
    exc_type_name: str


Event = OcrDone | TranslateStarted | TranslateDone | WarmedUp | JobCrashed


@dataclass(frozen=True)
class _WarmupResult:
    ok: bool


def ocr_job(png: bytes, deps: FlowDeps) -> Job:
    def job() -> Iterable[object]:
        yield ocr_flow(png, deps)

    return job


def code_ocr_job(png: bytes, deps: FlowDeps) -> Job:
    def job() -> Iterable[object]:
        yield code_ocr_flow(png, deps)

    return job


def table_ocr_job(png: bytes, deps: FlowDeps) -> Job:
    def job() -> Iterable[object]:
        yield table_ocr_flow(png, deps)

    return job


def translate_job(png: bytes, deps: FlowDeps, translator: Translator) -> Job:
    def job() -> Iterable[object]:
        stage = translate_ocr_stage(png, deps)
        if isinstance(stage, OcrStage):
            yield stage
            yield translate_stage(stage, translator)
        else:  # empty or failed OCR ends like the OCR action (plan A4)
            yield stage

    return job


def warmup_job(holder: EngineHolder) -> Job:
    """Load the engine ahead of the first OCR; a load failure waits for that OCR to report it (F7-4)."""

    def job() -> Iterable[object]:
        try:
            holder.get()
        except EngineLoadError:
            yield _WarmupResult(False)
        else:
            yield _WarmupResult(True)

    return job


_STOP = object()


class JobRunner:
    def __init__(
        self,
        on_event: Callable[[Event], None],
        history: ResultHistory,
        on_record: Callable[[int, HistoryRecord], None] | None = None,
    ) -> None:
        self._on_event = on_event
        self._history = history
        self._on_record = on_record  # F12: debug mode; called on the worker thread
        self._queue: queue.SimpleQueue[object] = queue.SimpleQueue()  # (job id, job)
        self._translate_queue: queue.SimpleQueue[object] = queue.SimpleQueue()  # (job id, the job's iterator)
        self._lock = threading.Lock()  # guards _next_id and the stopped check in submit
        self._deliver_lock = threading.RLock()  # a callback may call shutdown()
        self._stopped = threading.Event()
        self._next_id = 1
        self._thread = threading.Thread(target=self._run, args=(self._queue,), name=THREAD_NAME, daemon=True)
        self._translate_thread = threading.Thread(
            target=self._run, args=(self._translate_queue,), name=TRANSLATE_THREAD_NAME, daemon=True
        )
        self._thread.start()
        self._translate_thread.start()

    def submit(self, job: Job) -> int:
        with self._lock:
            if self._stopped.is_set():
                raise RuntimeError("job runner is shut down")
            job_id = self._next_id
            self._next_id += 1
            self._queue.put((job_id, lambda: iter(job())))
        return job_id

    def submit_warmup(self, holder: EngineHolder) -> int:
        return self.submit(warmup_job(holder))

    def shutdown(self, timeout: float = 0.5) -> None:
        """Stop taking jobs and drop queued ones; wait at most ``timeout`` seconds.

        No event is delivered after this returns, unless a callback is still
        running when ``timeout`` runs out.
        """
        if not (math.isfinite(timeout) and timeout >= 0):
            raise ValueError(f"timeout must be a finite number >= 0, got {timeout!r}")
        deadline = time.monotonic() + timeout
        got = self._deliver_lock.acquire(timeout=timeout)
        try:
            with self._lock:
                self._stopped.set()
                self._queue.put(_STOP)
                self._translate_queue.put(_STOP)
        finally:
            if got:
                self._deliver_lock.release()
        for thread in (self._thread, self._translate_thread):
            if threading.current_thread() is not thread:
                thread.join(max(0.0, deadline - time.monotonic()))

    def _run(self, jobs: queue.SimpleQueue[object]) -> None:
        while True:
            item = jobs.get()
            if item is _STOP or self._stopped.is_set():
                return
            job_id, start = item
            self._run_one(job_id, start)

    def _run_one(self, job_id: int, start: Callable[[], Iterator[object]]) -> None:
        try:
            results = start()
            for result in results:
                if self._stopped.is_set():
                    return
                if isinstance(result, OcrStage):
                    self._deliver(TranslateStarted(job_id, result))
                    if threading.current_thread() is self._thread:  # F18-1: the model request queues apart
                        self._translate_queue.put((job_id, lambda: results))
                        return
                    continue
                if isinstance(result, Outcome):
                    record, event = result.record, OcrDone(job_id, result)
                elif isinstance(result, TranslateOutcome):
                    record, event = result.record, TranslateDone(job_id, result)
                elif isinstance(result, _WarmupResult):
                    record, event = None, WarmedUp(job_id, result.ok)
                else:
                    raise TypeError(f"job yielded {type(result).__name__}, not a flow result")
                if record is not None:
                    self._history.push(record)
                    self._record_hook(job_id, record)
                self._deliver(event)
                return
            raise IncompleteJobError("job ended without a terminal result")
        except Exception as exc:
            # Type and frame locations only: the message may carry OCR text (CLAUDE.md privacy rule).
            frames = "".join(f"  {f.filename}:{f.lineno} in {f.name}\n" for f in traceback.extract_tb(exc.__traceback__))
            _log.error("job %d crashed: %s\n%s", job_id, type(exc).__name__, frames)
            self._deliver(JobCrashed(job_id, type(exc).__name__))

    def _record_hook(self, job_id: int, record: HistoryRecord) -> None:
        if self._on_record is None:
            return
        try:
            self._on_record(job_id, record)
        except Exception as exc:
            # The type only: the message may carry OCR text. The job's result is still delivered.
            _log.warning("on_record raised %s for job %d", type(exc).__name__, job_id)

    def _deliver(self, event: Event) -> None:
        with self._deliver_lock:
            if self._stopped.is_set():
                return
            try:
                self._on_event(event)
            except Exception:
                # Only the event type: payloads carry OCR text, which is not logged.
                _log.exception("on_event raised while handling %s", type(event).__name__)
