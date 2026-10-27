"""M2 WI-11: single-worker FIFO job runner (PRD F8-2, F7-5, F7-6; plan D2).

Pinned here:
- A job is a callable returning an iterable (usually a generator) of flow
  results. The runner turns each into an event tagged with the job id:
  ``OcrStage`` -> ``TranslateStarted``; ``Outcome`` -> ``OcrDone``;
  ``TranslateOutcome`` -> ``TranslateDone``. The last two are terminal.
- Every job ends with exactly one terminal event: ``OcrDone``,
  ``TranslateDone``, ``WarmedUp`` or ``JobCrashed``. Results after the
  terminal one are not consumed. A job that ends without a terminal result,
  yields anything else, or raises any ``Exception`` ends with
  ``JobCrashed(job_id, <exception type name>)``: ``IncompleteJobError`` for
  the first, ``TypeError`` for the second. The worker survives.
- A terminal result's ``record`` is pushed to the history on the worker
  thread before its event is delivered.
- Warm-up (plan D2) ends with ``WarmedUp(ok)``; an ``EngineLoadError`` is
  ``ok=False``, not a crash, and leaves no record.
- Job ids start at 1 and increase by one per submit.
- ``on_event`` runs on the worker thread ("snapocr-jobs", a daemon). An
  exception from it is logged (without the event) and the worker carries on.
- ``shutdown`` returns within ``timeout`` even while a job blocks; queued jobs
  are dropped, no event is delivered after it returns, and ``submit``
  afterwards raises ``RuntimeError``.
"""

import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from snapocr.actions.flows import FlowDeps, ocr_flow, translate_ocr_stage, translate_stage
from snapocr.actions.history import ResultHistory
from snapocr.actions.outcomes import (
    ClipboardText,
    Done,
    HistoryRecord,
    NoClipboardChange,
    Notice,
    OcrStage,
    Outcome,
)
from snapocr.actions.runner import (
    IncompleteJobError,
    JobCrashed,
    JobRunner,
    OcrDone,
    TranslateDone,
    TranslateStarted,
    WarmedUp,
    ocr_job,
    translate_job,
    warmup_job,
)
from snapocr.engines.errors import EngineLoadError
from snapocr.engines.holder import EngineHolder
from snapocr.engines.types import OcrResult
from snapocr.postprocess import PostprocessOptions, Replacements
from snapocr.translators.errors import TranslationError, TranslationErrorKind
from snapocr.translators.types import TranslationResult
from support.fake_actions import ScriptedEngine, ScriptedTranslator, holder_for
from support.pp_strategies import rect

PNG = b"\x89PNG\r\n\x1a\nfake"
RESULT = OcrResult((rect("你好，世界", 0, 0, 100, 20),))
OPTIONS = PostprocessOptions()
NO_TABLE = Replacements.from_mapping({})
TERMINAL = (OcrDone, TranslateDone, WarmedUp, JobCrashed)
LOAD_FAIL = EngineLoadError(model_paths=(), hint="h", detail="d")
WAIT_S = 10
TESTS_DIR = Path(__file__).resolve().parents[1]


def deps(behaviour=RESULT, **kw) -> FlowDeps:
    return FlowDeps(holder_for(behaviour, **kw), OPTIONS, NO_TABLE)


def tr_error(kind=TranslationErrorKind.TIMEOUT) -> TranslationError:
    return TranslationError(kind, base_url="http://127.0.0.1:11434", model="hy-mt2:7b", detail="x")


class Collector:
    """Records (event, thread id); ``wait_terminal(n)`` blocks until n terminal events."""

    def __init__(self):
        self.items: list[tuple[object, int]] = []
        self._cond = threading.Condition()

    def __call__(self, event):
        with self._cond:
            self.items.append((event, threading.get_ident()))
            self._cond.notify_all()

    @property
    def events(self):
        with self._cond:
            return [e for e, _ in self.items]

    def wait_terminal(self, n: int) -> list:
        with self._cond:
            ok = self._cond.wait_for(
                lambda: sum(isinstance(e, TERMINAL) for e, _ in self.items) >= n, timeout=WAIT_S
            )
        assert ok, f"timed out waiting for {n} terminal events; got {self.events}"
        return [e for e in self.events if isinstance(e, TERMINAL)]


@pytest.fixture
def make_runner():
    runners = []

    def make(on_event=None, history=None):
        collector = on_event if on_event is not None else Collector()
        runner = JobRunner(collector, history if history is not None else ResultHistory())
        runners.append(runner)
        return runner, collector

    yield make
    for r in runners:
        r.shutdown()


def outcome_job(tag: str, delay: float = 0.0):
    record = HistoryRecord(b"", tag, tag)

    def job():
        if delay:
            time.sleep(delay)  # simulated work, not polling
        yield Outcome(ClipboardText(tag), None, record)

    return job


def blocking_job(release: threading.Event, started: threading.Event):
    def job():
        started.set()
        release.wait(60)
        yield Outcome(NoClipboardChange(), None, None)

    return job


# --- examples -------------------------------------------------------------


def test_three_jobs_complete_in_submission_order(make_runner):
    runner, col = make_runner()
    ids = [runner.submit(outcome_job(t)) for t in ("a", "b", "c")]
    done = col.wait_terminal(3)
    assert ids == [1, 2, 3]
    assert [(e.job_id, e.outcome.clipboard.text) for e in done] == [(1, "a"), (2, "b"), (3, "c")]


def test_ocr_job_delivers_ocr_flow_outcome_and_records_it(make_runner):
    history = ResultHistory()
    runner, col = make_runner(history=history)
    d = deps()
    job_id = runner.submit(ocr_job(PNG, d))
    (event,) = col.wait_terminal(1)
    expected = ocr_flow(PNG, d)
    assert event == OcrDone(job_id, expected)
    assert event.outcome.clipboard == ClipboardText("你好，世界")
    assert history.snapshot() == (expected.record,)


def test_translate_job_emits_started_with_postprocessed_text_then_done(make_runner):
    history = ResultHistory()
    runner, col = make_runner(history=history)
    d = deps()
    job_id = runner.submit(translate_job(PNG, d, ScriptedTranslator()))
    col.wait_terminal(1)
    stage = translate_ocr_stage(PNG, d)
    assert isinstance(stage, OcrStage)
    expected = translate_stage(stage, ScriptedTranslator())
    assert col.events == [TranslateStarted(job_id, stage), TranslateDone(job_id, expected)]
    assert col.events[0].stage.text == "你好，世界"
    assert expected.popup == Done("你好，世界", "T(你好，世界)")
    assert history.snapshot() == (expected.record,)


def test_translate_job_with_translation_error_ends_in_translate_done(make_runner):
    runner, col = make_runner()
    runner.submit(translate_job(PNG, deps(), ScriptedTranslator(tr_error())))
    (event,) = col.wait_terminal(1)
    assert isinstance(event, TranslateDone)
    assert event.outcome.clipboard == NoClipboardChange()


@pytest.mark.parametrize("load_error", [None, LOAD_FAIL], ids=["empty", "load-fail"])
def test_translate_job_without_text_ends_like_ocr_without_started(make_runner, load_error):
    """Plan A4: empty OCR or engine failure ends with OcrDone; no TranslateStarted."""
    runner, col = make_runner()
    d = deps(OcrResult(()), load_error=load_error)
    job_id = runner.submit(translate_job(PNG, d, ScriptedTranslator()))
    col.wait_terminal(1)
    assert col.events == [OcrDone(job_id, translate_ocr_stage(PNG, d))]


def test_callbacks_run_on_the_worker_thread(make_runner):
    runner, col = make_runner()
    runner.submit(outcome_job("a"))
    runner.submit(translate_job(PNG, deps(), ScriptedTranslator()))
    col.wait_terminal(2)
    threads = {tid for _, tid in col.items}
    assert len(col.items) == 3
    assert len(threads) == 1
    assert threading.get_ident() not in threads


# --- crashes and warm-up ----------------------------------------------------


def test_runtime_error_crashes_one_job_and_later_jobs_complete(make_runner):
    history = ResultHistory()
    runner, col = make_runner(history=history)

    def bad():
        yield from ()
        raise RuntimeError("boom")

    runner.submit(outcome_job("a"))
    runner.submit(bad)
    runner.submit(outcome_job("c"))
    done = col.wait_terminal(3)
    assert done[1] == JobCrashed(2, "RuntimeError")
    assert [type(e) for e in done] == [OcrDone, JobCrashed, OcrDone]
    assert [r.text for r in history.snapshot()] == ["c", "a"]


def test_exception_from_a_plain_callable_is_a_crash(make_runner):
    runner, col = make_runner()

    def bad():
        raise KeyError("x")

    runner.submit(bad)
    assert col.wait_terminal(1) == [JobCrashed(1, "KeyError")]


def test_unexpected_engine_exception_in_ocr_job_is_a_crash(make_runner):
    """Only OcrError is handled by the flow; anything else reaches the runner."""
    runner, col = make_runner()
    runner.submit(ocr_job(PNG, deps(ValueError("not an OcrError"))))
    runner.submit(ocr_job(PNG, deps()))
    done = col.wait_terminal(2)
    assert done[0] == JobCrashed(1, "ValueError")
    assert isinstance(done[1], OcrDone)


def test_crash_after_translate_started_still_ends_the_job(make_runner):
    runner, col = make_runner()
    runner.submit(translate_job(PNG, deps(), ScriptedTranslator(ZeroDivisionError())))
    col.wait_terminal(1)
    assert [type(e) for e in col.events] == [TranslateStarted, JobCrashed]
    assert col.events[1] == JobCrashed(1, "ZeroDivisionError")


def test_job_without_terminal_result_is_incomplete(make_runner):
    runner, col = make_runner()
    stage = OcrStage(PNG, "r", "t")
    runner.submit(lambda: iter([stage]))
    runner.submit(lambda: [])
    col.wait_terminal(2)
    assert col.events == [
        TranslateStarted(1, stage),
        JobCrashed(1, "IncompleteJobError"),
        JobCrashed(2, "IncompleteJobError"),
    ]
    assert issubclass(IncompleteJobError, RuntimeError)


@pytest.mark.parametrize("value", ["not a result", None, WarmedUp(99, True)], ids=["str", "none", "event"])
def test_any_other_yielded_value_is_a_type_error_crash(make_runner, value):
    history = ResultHistory()
    runner, col = make_runner(history=history)
    runner.submit(lambda: iter([value]))
    assert col.wait_terminal(1) == [JobCrashed(1, "TypeError")]
    assert history.snapshot() == ()


def test_job_returning_a_non_iterable_is_a_type_error_crash(make_runner):
    runner, col = make_runner()
    runner.submit(lambda: 42)
    assert col.wait_terminal(1) == [JobCrashed(1, "TypeError")]


def test_results_after_the_terminal_one_are_not_consumed(make_runner):
    history = ResultHistory()
    runner, col = make_runner(history=history)
    consumed = []

    def job():
        consumed.append(1)
        yield Outcome(ClipboardText("first"), None, HistoryRecord(b"", "1", "1"))
        consumed.append(2)
        yield Outcome(ClipboardText("second"), None, HistoryRecord(b"", "2", "2"))

    runner.submit(job)
    runner.submit(outcome_job("next"))
    col.wait_terminal(2)
    assert [e.outcome.clipboard.text for e in col.events] == ["first", "next"]
    assert consumed == [1]
    assert [r.text for r in history.snapshot()] == ["next", "1"]


def test_outcome_without_record_adds_nothing_to_history(make_runner):
    history = ResultHistory()
    runner, col = make_runner(history=history)
    runner.submit(lambda: iter([Outcome(NoClipboardChange(), Notice("t", ""), None)]))
    col.wait_terminal(1)
    assert history.snapshot() == ()


def test_record_is_in_history_when_its_event_is_delivered(make_runner):
    history = ResultHistory()
    col = Collector()
    seen = []

    def on_event(event):
        seen.append(tuple(r.text for r in history.snapshot()))
        col(event)

    runner, _ = make_runner(on_event=on_event, history=history)
    runner.submit(outcome_job("a"))
    runner.submit(translate_job(PNG, deps(), ScriptedTranslator()))
    col.wait_terminal(2)
    # OcrDone(a), TranslateStarted (no record yet), TranslateDone
    assert seen == [("a",), ("a",), ("你好，世界", "a")]


def test_warmup_success(make_runner):
    runner, col = make_runner()
    job_id = runner.submit_warmup(holder_for(RESULT))
    assert col.wait_terminal(1) == [WarmedUp(job_id, True)]


def test_warmup_failure_is_not_a_crash_and_leaves_no_record(make_runner):
    history = ResultHistory()
    runner, col = make_runner(history=history)
    holder = holder_for(RESULT, load_error=LOAD_FAIL)
    runner.submit_warmup(holder)
    runner.submit(ocr_job(PNG, FlowDeps(holder, OPTIONS, NO_TABLE)))
    done = col.wait_terminal(2)
    assert done[0] == WarmedUp(1, False)
    assert isinstance(done[1], OcrDone)
    assert done[1].outcome.clipboard == NoClipboardChange()  # F7-4 is reported by the OCR job
    assert len(history.snapshot()) == 1


def test_warmup_with_a_wrapped_factory_error_is_not_ok(make_runner):
    def factory():
        raise OSError("disk")  # EngineHolder wraps it into EngineLoadError

    runner, col = make_runner()
    runner.submit(warmup_job(EngineHolder(factory)))
    assert col.wait_terminal(1) == [WarmedUp(1, False)]


def test_warmup_with_an_unexpected_exception_is_a_crash(make_runner):
    class BrokenHolder:
        def get(self):
            raise ValueError("not a load error")

    runner, col = make_runner()
    runner.submit_warmup(BrokenHolder())
    assert col.wait_terminal(1) == [JobCrashed(1, "ValueError")]


def test_warmup_loads_the_engine_once_for_later_ocr(make_runner):
    loads = []

    def factory():
        loads.append(1)
        return ScriptedEngine(RESULT)

    holder = EngineHolder(factory)
    runner, col = make_runner()
    runner.submit_warmup(holder)
    runner.submit(ocr_job(PNG, FlowDeps(holder, OPTIONS, NO_TABLE)))
    done = col.wait_terminal(2)
    assert done[0] == WarmedUp(1, True)
    assert done[1].outcome.clipboard == ClipboardText("你好，世界")
    assert loads == [1]


# --- on_event failures ------------------------------------------------------


def test_on_event_exception_is_logged_and_worker_continues(make_runner, caplog):
    col = Collector()
    calls = []

    def on_event(event):
        calls.append(event)
        if len(calls) == 1:
            raise RuntimeError("callback broke")
        col(event)

    runner, _ = make_runner(on_event=on_event)
    with caplog.at_level("ERROR", logger="snapocr.actions.runner"):
        runner.submit(outcome_job("secret-ocr-text"))
        runner.submit(outcome_job("b"))
        done = col.wait_terminal(1)
    assert [e.outcome.clipboard.text for e in done] == ["b"]
    errors = [r for r in caplog.records if r.name == "snapocr.actions.runner"]
    assert len(errors) == 1
    assert errors[0].exc_info[0] is RuntimeError
    assert "secret-ocr-text" not in errors[0].getMessage()  # the event payload is not logged


# --- shutdown ---------------------------------------------------------------


def test_shutdown_returns_quickly_while_a_job_blocks(make_runner):
    runner, col = make_runner()
    release, started = threading.Event(), threading.Event()
    runner.submit(blocking_job(release, started))
    runner.submit(outcome_job("queued"))
    assert started.wait(WAIT_S)
    t0 = time.monotonic()
    runner.shutdown(timeout=0.5)
    elapsed = time.monotonic() - t0
    release.set()
    assert elapsed < 1.0
    time.sleep(0.2)  # give a misbehaving worker the chance to deliver
    assert col.events == []


def test_submit_after_shutdown_raises(make_runner):
    runner, _ = make_runner()
    runner.shutdown()
    with pytest.raises(RuntimeError, match="shut down"):
        runner.submit(outcome_job("x"))
    with pytest.raises(RuntimeError, match="shut down"):
        runner.submit_warmup(holder_for(RESULT))


def test_shutdown_is_idempotent_and_joins_an_idle_worker(make_runner):
    runner, col = make_runner()
    runner.submit(outcome_job("a"))
    col.wait_terminal(1)
    t0 = time.monotonic()
    runner.shutdown()
    runner.shutdown()
    assert time.monotonic() - t0 < 1.0
    assert not any(t.name == "snapocr-jobs" and t.is_alive() for t in threading.enumerate())


@pytest.mark.parametrize("timeout", [-1, float("nan"), float("inf")])
def test_shutdown_rejects_bad_timeout(make_runner, timeout):
    runner, _ = make_runner()
    with pytest.raises(ValueError, match="timeout"):
        runner.shutdown(timeout=timeout)


def test_shutdown_with_zero_timeout_does_not_wait(make_runner):
    runner, col = make_runner()
    release, started = threading.Event(), threading.Event()
    runner.submit(blocking_job(release, started))
    assert started.wait(WAIT_S)
    t0 = time.monotonic()
    runner.shutdown(timeout=0)
    assert time.monotonic() - t0 < 0.2
    release.set()


def test_worker_is_a_daemon_thread(make_runner):
    before = {t.ident for t in threading.enumerate()}
    make_runner()
    new = [t for t in threading.enumerate() if t.ident not in before]
    assert len(new) == 1
    assert new[0].daemon
    assert new[0].name == "snapocr-jobs"


EXIT_SCRIPT = textwrap.dedent(
    """
    import sys, threading, time
    sys.path.insert(0, sys.argv[1])
    from snapocr.actions.flows import FlowDeps
    from snapocr.actions.history import ResultHistory
    from snapocr.actions.runner import JobRunner, translate_job
    from snapocr.engines.types import OcrResult
    from snapocr.postprocess import PostprocessOptions, Replacements
    from support.fake_actions import holder_for
    from support.pp_strategies import rect

    started = threading.Event()

    class Blocking:
        def translate(self, text):
            started.set()
            threading.Event().wait(60)

    deps = FlowDeps(holder_for(OcrResult((rect("x", 0, 0, 10, 10),))), PostprocessOptions(), Replacements.from_mapping({}))
    runner = JobRunner(lambda e: None, ResultHistory())
    runner.submit(translate_job(b"png", deps, Blocking()))
    assert started.wait(10)
    t0 = time.monotonic()
    runner.shutdown()
    print(round(time.monotonic() - t0, 3), flush=True)
    sys.exit(0)
    """
)


def test_process_exits_while_translation_blocks():
    proc = subprocess.Popen(
        [sys.executable, "-c", EXIT_SCRIPT, str(TESTS_DIR)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        line = proc.stdout.readline()  # printed after imports and shutdown, just before sys.exit
        t0 = time.monotonic()
        proc.wait(timeout=3)
        exit_s = time.monotonic() - t0
    finally:
        proc.kill()
        proc.communicate()
    assert proc.returncode == 0
    assert float(line) < 1.0
    assert exit_s < 3.0


# --- properties -------------------------------------------------------------


@settings(max_examples=25, deadline=None)
@given(delays=st.lists(st.sampled_from([0.0, 0.0005, 0.001, 0.002]), min_size=1, max_size=20))
def test_terminal_events_follow_submission_order(delays):
    col = Collector()
    runner = JobRunner(col, ResultHistory())
    try:
        ids = [runner.submit(outcome_job(str(i), d)) for i, d in enumerate(delays)]
        done = col.wait_terminal(len(ids))
    finally:
        runner.shutdown()
    assert ids == list(range(1, len(ids) + 1))
    assert [e.job_id for e in done] == ids
    assert [e.outcome.clipboard.text for e in done] == [str(i) for i in range(len(delays))]


def _job_for(kind: str):
    if kind == "ocr_ok":
        return ocr_job(PNG, deps())
    if kind == "ocr_empty":
        return ocr_job(PNG, deps(OcrResult(())))
    if kind == "ocr_load_fail":
        return ocr_job(PNG, deps(load_error=LOAD_FAIL))
    if kind == "tr_ok":
        return translate_job(PNG, deps(), ScriptedTranslator())
    if kind == "tr_err":
        return translate_job(PNG, deps(), ScriptedTranslator(tr_error(TranslationErrorKind.HTTP_STATUS)))
    if kind == "tr_skip":
        return translate_job(PNG, deps(), ScriptedTranslator(TranslationResult("", None, True)))
    if kind == "tr_empty":
        return translate_job(PNG, deps(OcrResult(())), ScriptedTranslator())
    if kind == "crash":
        return ocr_job(PNG, deps(RuntimeError("x")))
    if kind == "warmup":
        return warmup_job(holder_for(RESULT))
    assert kind == "warmup_fail"
    return warmup_job(holder_for(RESULT, load_error=LOAD_FAIL))


EXPECTED_TERMINAL = {
    "ocr_ok": OcrDone,
    "ocr_empty": OcrDone,
    "ocr_load_fail": OcrDone,
    "tr_ok": TranslateDone,
    "tr_err": TranslateDone,
    "tr_skip": TranslateDone,
    "tr_empty": OcrDone,
    "crash": JobCrashed,
    "warmup": WarmedUp,
    "warmup_fail": WarmedUp,
}
RECORDED = {"ocr_ok", "ocr_empty", "ocr_load_fail", "tr_ok", "tr_err", "tr_skip", "tr_empty"}


@settings(max_examples=25, deadline=None)
@given(kinds=st.lists(st.sampled_from(sorted(EXPECTED_TERMINAL)), min_size=1, max_size=12))
def test_one_terminal_event_per_job_and_one_record_per_ocr_or_translate(kinds):
    history = ResultHistory(capacity=50)
    col = Collector()
    runner = JobRunner(col, history)
    try:
        ids = [runner.submit(_job_for(k)) for k in kinds]
        done = col.wait_terminal(len(ids))
    finally:
        runner.shutdown(timeout=WAIT_S)
    assert [e.job_id for e in done] == ids
    assert [type(e) for e in done] == [EXPECTED_TERMINAL[k] for k in kinds]
    assert len(history.snapshot()) == sum(k in RECORDED for k in kinds)
    started = [e.job_id for e in col.events if isinstance(e, TranslateStarted)]
    assert started == [i for i, k in zip(ids, kinds) if k in ("tr_ok", "tr_err", "tr_skip")]


# --- shutdown edge cases (added after the first green: coverage) ------------


def test_callback_may_shut_the_runner_down(make_runner):
    col = Collector()
    holder = {}

    def on_event(event):
        col(event)
        holder["runner"].shutdown()

    runner, _ = make_runner(on_event=on_event)
    holder["runner"] = runner
    runner.submit(outcome_job("a"))
    runner.submit(outcome_job("b"))
    col.wait_terminal(1)
    runner._thread.join(WAIT_S)
    assert not runner._thread.is_alive()
    assert [e.outcome.clipboard.text for e in col.events] == ["a"]
    with pytest.raises(RuntimeError, match="shut down"):
        runner.submit(outcome_job("c"))


def test_shutdown_waits_at_most_timeout_while_a_callback_blocks(make_runner):
    in_callback, release = threading.Event(), threading.Event()
    col = Collector()

    def on_event(event):
        col(event)
        if len(col.events) == 1:
            in_callback.set()
            release.wait(60)

    runner, _ = make_runner(on_event=on_event)
    runner.submit(outcome_job("a"))
    runner.submit(outcome_job("b"))
    assert in_callback.wait(WAIT_S)
    t0 = time.monotonic()
    runner.shutdown(timeout=0.3)
    elapsed = time.monotonic() - t0
    release.set()
    runner._thread.join(WAIT_S)
    assert 0.25 <= elapsed < 0.55  # one budget for the lock and the join together
    assert [e.outcome.clipboard.text for e in col.events] == ["a"]


def test_a_job_crashing_after_shutdown_delivers_nothing(make_runner):
    runner, col = make_runner()
    release, started = threading.Event(), threading.Event()

    def job():
        started.set()
        release.wait(60)
        raise RuntimeError("after shutdown")
        yield  # makes this a generator

    runner.submit(job)
    assert started.wait(WAIT_S)
    runner.shutdown(timeout=0)
    release.set()
    runner._thread.join(WAIT_S)
    assert not runner._thread.is_alive()
    assert col.events == []


# --- FIX-3: a crash is logged (type and traceback, not the message) ---------------------


def test_crash_is_logged_without_the_exception_message(make_runner, caplog):
    runner, col = make_runner()

    def leaky_crash():
        yield from ()
        raise ValueError("secret-ocr-text in the message")

    with caplog.at_level("ERROR", logger="snapocr.actions.runner"):
        runner.submit(leaky_crash)
        assert col.wait_terminal(1) == [JobCrashed(1, "ValueError")]
    records = [r for r in caplog.records if r.name == "snapocr.actions.runner"]
    assert len(records) == 1
    text = caplog.text
    assert "job 1 crashed: ValueError" in records[0].getMessage()
    assert "leaky_crash" in text  # the traceback names the frame
    assert "secret-ocr-text" not in text
    assert records[0].exc_info is None  # exc_info would print str(exc)


def test_handled_failures_are_not_logged_as_crashes(make_runner, caplog):
    runner, col = make_runner()
    with caplog.at_level("ERROR", logger="snapocr.actions.runner"):
        runner.submit(ocr_job(PNG, deps(load_error=LOAD_FAIL)))
        runner.submit(translate_job(PNG, deps(), ScriptedTranslator(tr_error())))
        runner.submit_warmup(holder_for(RESULT, load_error=LOAD_FAIL))
        col.wait_terminal(3)
    assert [r for r in caplog.records if r.name == "snapocr.actions.runner"] == []


# --- M3 WI-12: on_record hook for debug mode (F12-1, F12-3) ------------------------------

import logging  # noqa: E402


def test_on_record_gets_each_record_after_history_and_before_the_event():
    history = ResultHistory()
    col = Collector()
    calls = []

    def on_record(job_id, record):
        calls.append((job_id, record.text, tuple(r.text for r in history.snapshot()), len(col.events)))

    runner = JobRunner(col, history, on_record=on_record)
    try:
        a = runner.submit(outcome_job("a"))
        w = runner.submit(warmup_job(holder_for(RESULT)))
        t = runner.submit(translate_job(PNG, deps(), ScriptedTranslator()))
        col.wait_terminal(3)
    finally:
        runner.shutdown()
    assert w == a + 1 and t == a + 2
    # (job id, record text, history at that moment, events delivered before it)
    assert calls == [(a, "a", ("a",), 0), (t, "你好，世界", ("你好，世界", "a"), 3)]


def test_on_record_failure_is_logged_and_the_event_still_arrives(caplog):
    col = Collector()

    def on_record(job_id, record):
        raise ValueError(f"boom {record.text}")

    runner = JobRunner(col, ResultHistory(), on_record=on_record)
    try:
        with caplog.at_level(logging.WARNING, logger="snapocr.actions.runner"):
            runner.submit(outcome_job("secret-text"))
            [done] = col.wait_terminal(1)
            runner.submit(outcome_job("b"))
            col.wait_terminal(2)
    finally:
        runner.shutdown()
    assert isinstance(done, OcrDone)
    messages = [r.getMessage() for r in caplog.records if r.name == "snapocr.actions.runner"]
    assert messages == ["on_record raised ValueError for job 1", "on_record raised ValueError for job 2"]
    assert all("secret-text" not in r.getMessage() and r.exc_info is None for r in caplog.records)


def test_without_on_record_nothing_changes(make_runner):
    runner, col = make_runner()
    runner.submit(outcome_job("a"))
    assert isinstance(col.wait_terminal(1)[0], OcrDone)
