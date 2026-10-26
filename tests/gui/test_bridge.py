"""M2 WI-13: runner events reach the GUI thread through EventBridge (plan D2, F8-2).

Pinned here:
- ``post`` may be called from any thread; the ``event`` signal's slots run on
  the GUI (main) thread, with the same object, in posting order.
- ``post`` from the GUI thread itself is delivered too.
- With a real ``JobRunner(on_event=bridge.post)``, the runner's events arrive
  on the GUI thread in the runner's order.
"""

import threading

import pytest

from snapocr.actions.flows import FlowDeps
from snapocr.actions.history import ResultHistory
from snapocr.actions.runner import JobRunner, OcrDone, TranslateDone, TranslateStarted, ocr_job, translate_job
from snapocr.engines.types import OcrResult
from snapocr.gui.bridge import EventBridge
from snapocr.postprocess import PostprocessOptions, Replacements
from support.fake_actions import ScriptedTranslator, holder_for
from support.pp_strategies import rect

MAIN = threading.main_thread().ident
PNG = b"\x89PNG\r\n\x1a\nfake"


@pytest.fixture
def bridge(qapp):
    return EventBridge()


def test_event_from_worker_thread_arrives_on_gui_thread(qtbot, bridge):
    seen = []
    bridge.event.connect(lambda e: seen.append((e, threading.get_ident())))
    payload = object()
    worker = threading.Thread(target=bridge.post, args=(payload,))
    with qtbot.waitSignal(bridge.event, timeout=5000) as blocker:
        worker.start()
    worker.join(5)
    assert blocker.args == [payload]
    assert seen == [(payload, MAIN)]
    assert worker.ident != MAIN


def test_many_events_keep_order(qtbot, bridge):
    seen = []
    bridge.event.connect(lambda e: seen.append((e, threading.get_ident())))

    def burst():
        for i in range(200):
            bridge.post(i)

    worker = threading.Thread(target=burst)
    worker.start()
    worker.join(5)
    qtbot.waitUntil(lambda: len(seen) == 200, timeout=5000)
    assert [e for e, _ in seen] == list(range(200))
    assert {t for _, t in seen} == {MAIN}


def test_post_from_gui_thread_is_delivered(qtbot, bridge):
    seen = []
    bridge.event.connect(seen.append)
    bridge.post("x")
    qtbot.waitUntil(lambda: seen == ["x"], timeout=2000)


def test_runner_events_arrive_on_gui_thread_in_order(qtbot, bridge):
    seen = []
    bridge.event.connect(lambda e: seen.append((e, threading.get_ident())))
    deps = FlowDeps(holder_for(OcrResult((rect("你好", 0, 0, 40, 20),))), PostprocessOptions(), Replacements.from_mapping({}))
    runner = JobRunner(bridge.post, ResultHistory())
    try:
        runner.submit(ocr_job(PNG, deps))
        runner.submit(translate_job(PNG, deps, ScriptedTranslator()))
        qtbot.waitUntil(lambda: len(seen) == 3, timeout=5000)
    finally:
        runner.shutdown()
    assert [type(e) for e, _ in seen] == [OcrDone, TranslateStarted, TranslateDone]
    assert [e.job_id for e, _ in seen] == [1, 2, 2]
    assert {t for _, t in seen} == {MAIN}
