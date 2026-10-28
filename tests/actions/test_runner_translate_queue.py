"""M5 WI-1: the model request of a translation has its own queue (PRD F18-1; M5 plan D3).

Pinned here:
- Recognition still runs one job at a time in submission order, on
  "snapocr-jobs". When a translate job reaches its ``OcrStage``, the rest of
  it (the model request) moves to "snapocr-translate"; recognition goes on
  with the next job meanwhile.
- So an OCR submitted after a translation that waits for the model ends
  first, and the translation still ends with its ``TranslateDone`` later.
- Model requests run one at a time, in submission order.
- A crash in the model request ends that job with ``JobCrashed``; both
  workers carry on.
- After ``shutdown`` neither queue delivers anything, also when a model
  request returns later.
"""

import threading
import time

from snapocr.actions.flows import FlowDeps
from snapocr.actions.runner import JobCrashed, JobRunner, OcrDone, TranslateDone, TranslateStarted, ocr_job, translate_job
from snapocr.engines.types import OcrResult
from snapocr.postprocess import PostprocessOptions, Replacements
from snapocr.translators.types import TranslationResult
from support.fake_actions import holder_for
from support.pp_strategies import rect

PNG = b"\x89PNG\r\n\x1a\nfake"
WAIT_S = 10


def deps(text="你好") -> FlowDeps:
    return FlowDeps(holder_for(OcrResult((rect(text, 0, 0, 100, 20),))), PostprocessOptions(), Replacements.from_mapping({}))


class Events:
    """Thread-safe event log with ``wait_for(predicate)``."""

    def __init__(self):
        self.items: list[tuple[object, str]] = []
        self._cond = threading.Condition()

    def __call__(self, event):
        with self._cond:
            self.items.append((event, threading.current_thread().name))
            self._cond.notify_all()

    @property
    def events(self):
        with self._cond:
            return [e for e, _ in self.items]

    def wait_for(self, predicate, what):
        with self._cond:
            ok = self._cond.wait_for(lambda: predicate([e for e, _ in self.items]), timeout=WAIT_S)
        assert ok, f"timed out waiting for {what}; got {self.events}"


class GatedTranslator:
    """Each request waits for its own gate; records the order and the most requests running at once."""

    def __init__(self):
        self.gates: dict[str, threading.Event] = {}
        self.calls: list[str] = []
        self.running = 0
        self.most = 0
        self.entered = threading.Event()  # set once the first request has started
        self._lock = threading.Lock()

    def gate(self, text: str) -> threading.Event:
        return self.gates.setdefault(text, threading.Event())

    def translate(self, text: str, target=None) -> TranslationResult:
        with self._lock:
            self.calls.append(text)
            self.running += 1
            self.most = max(self.most, self.running)
            self.entered.set()
        try:
            self.gate(text).wait(WAIT_S)
            return TranslationResult(f"T({text})", "en", False)
        finally:
            with self._lock:
                self.running -= 1


def done_ids(events, kind):
    return [e.job_id for e in events if isinstance(e, kind)]


def test_ocr_is_not_held_up_by_a_translation_waiting_for_the_model():
    log, tr = Events(), GatedTranslator()
    runner = JobRunner(log)
    try:
        t = runner.submit(translate_job(PNG, deps("原文"), tr))
        o = runner.submit(ocr_job(PNG, deps("另一段")))
        log.wait_for(lambda ev: o in done_ids(ev, OcrDone), "the OCR to finish while the model waits")
        assert done_ids(log.events, TranslateDone) == []
        assert tr.entered.wait(WAIT_S)
        assert tr.calls == ["原文"]
        tr.gate("原文").set()
        log.wait_for(lambda ev: t in done_ids(ev, TranslateDone), "the translation to finish")
    finally:
        runner.shutdown()
    events = log.events
    assert [type(e) for e in events] == [TranslateStarted, OcrDone, TranslateDone]
    assert events[2].outcome.popup.translation == "T(原文)"
    names = {type(e): name for e, name in log.items}
    assert names == {TranslateStarted: "snapocr-jobs", OcrDone: "snapocr-jobs", TranslateDone: "snapocr-translate"}


def test_model_requests_run_one_at_a_time_in_order():
    log, tr = Events(), GatedTranslator()
    runner = JobRunner(log)
    try:
        first = runner.submit(translate_job(PNG, deps("一"), tr))
        second = runner.submit(translate_job(PNG, deps("二"), tr))
        # Both recognitions finish although the first model request still waits.
        log.wait_for(lambda ev: done_ids(ev, TranslateStarted) == [first, second], "both recognitions")
        assert tr.entered.wait(WAIT_S)
        time.sleep(0.05)  # give a second request the chance to start, if it would
        assert tr.calls == ["一"]
        tr.gate("二").set()  # the second may not overtake the first
        time.sleep(0.05)
        assert done_ids(log.events, TranslateDone) == []
        tr.gate("一").set()
        log.wait_for(lambda ev: len(done_ids(ev, TranslateDone)) == 2, "both translations")
    finally:
        runner.shutdown()
    assert done_ids(log.events, TranslateDone) == [first, second]
    assert tr.calls == ["一", "二"]
    assert tr.most == 1


class CrashingTranslator:
    def translate(self, text, target=None):
        raise RuntimeError("boom")


def test_a_crash_in_the_model_request_ends_that_job_and_both_queues_go_on():
    log, tr = Events(), GatedTranslator()
    runner = JobRunner(log)
    try:
        bad = runner.submit(translate_job(PNG, deps("坏"), CrashingTranslator()))
        log.wait_for(lambda ev: bad in done_ids(ev, JobCrashed), "the crash")
        good = runner.submit(translate_job(PNG, deps("好"), tr))
        tr.gate("好").set()
        o = runner.submit(ocr_job(PNG, deps()))
        log.wait_for(lambda ev: good in done_ids(ev, TranslateDone) and o in done_ids(ev, OcrDone), "the next jobs")
    finally:
        runner.shutdown()
    crashed = [(e, name) for e, name in log.items if isinstance(e, JobCrashed)]
    assert crashed == [(JobCrashed(bad, "RuntimeError"), "snapocr-translate")]


def test_nothing_arrives_after_shutdown_when_the_model_answers_later():
    log, tr = Events(), GatedTranslator()
    runner = JobRunner(log)
    runner.submit(translate_job(PNG, deps("迟"), tr))
    log.wait_for(lambda ev: len(done_ids(ev, TranslateStarted)) == 1, "the recognition")
    t0 = time.monotonic()
    runner.shutdown(timeout=0.5)
    assert time.monotonic() - t0 < 1.0
    tr.gate("迟").set()
    time.sleep(0.2)  # give a misbehaving worker the chance to deliver
    assert [type(e) for e in log.events] == [TranslateStarted]


def test_both_workers_stop_on_shutdown():
    before = set(threading.enumerate())
    log, tr = Events(), GatedTranslator()
    runner = JobRunner(log)
    workers = [t for t in threading.enumerate() if t not in before]
    tr.gate("你好").set()
    runner.submit(translate_job(PNG, deps(), tr))
    log.wait_for(lambda ev: len(done_ids(ev, TranslateDone)) == 1, "the translation")
    runner.shutdown()
    for t in workers:
        t.join(WAIT_S)
    assert sorted(t.name for t in workers) == ["snapocr-jobs", "snapocr-translate"]
    assert [t.name for t in workers if t.is_alive()] == []


def test_a_second_ocr_stage_on_the_translate_worker_is_reported_and_the_job_goes_on():
    from snapocr.actions.outcomes import ClipboardText, OcrStage, Outcome

    log = Events()
    runner = JobRunner(log)
    first, second = OcrStage(PNG, "a", "a"), OcrStage(PNG, "b", "b")
    try:
        runner.submit(lambda: iter([first, second, Outcome(ClipboardText("x"), None, None)]))
        log.wait_for(lambda ev: len(done_ids(ev, OcrDone)) == 1, "the job to end")
    finally:
        runner.shutdown()
    assert [(e, name) for e, name in log.items][:2] == [
        (TranslateStarted(1, first), "snapocr-jobs"),
        (TranslateStarted(1, second), "snapocr-translate"),
    ]
    assert [type(e) for e in log.events] == [TranslateStarted, TranslateStarted, OcrDone]
