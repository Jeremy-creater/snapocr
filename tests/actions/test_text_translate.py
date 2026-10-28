"""M6 WI-2: target language for translate jobs, and the text translate job (PRD F19-5, F19-6, F12-1; plan D7, D8).

Pinned here:
- ``translate_stage`` and ``translate_job`` pass the target to the translator;
  ``None`` (the default) leaves the direction to the translator's config.
- ``text_translate_job(text, translator, target)`` translates ``text`` as
  typed: ``TranslateStarted`` (from the recognition worker) then
  ``TranslateDone`` (from the translate worker), like a screenshot translation.
- A text translation keeps no record, so debug mode writes nothing for it.
"""

import threading

import pytest

from snapocr.actions.flows import FlowDeps, translate_stage
from snapocr.actions.outcomes import ClipboardText, Done, Failed, NoClipboardChange, OcrStage
from snapocr.actions.runner import JobRunner, TranslateDone, TranslateStarted, text_translate_job, translate_job
from snapocr.engines.types import OcrResult
from snapocr.postprocess import PostprocessOptions, Replacements
from snapocr.translators.errors import TranslationError, TranslationErrorKind
from snapocr.translators.types import TranslationResult
from support.fake_actions import ScriptedTranslator, holder_for
from support.pp_strategies import rect

PNG = b"\x89PNG\r\n\x1a\nfake"
STAGE = OcrStage(PNG, "你好", "你好")
WAIT_S = 10


def deps(text="你好") -> FlowDeps:
    return FlowDeps(holder_for(OcrResult((rect(text, 0, 0, 100, 20),))), PostprocessOptions(), Replacements.from_mapping({}))


class Log:
    def __init__(self):
        self.items = []
        self.done = threading.Event()

    def __call__(self, event):
        self.items.append((event, threading.current_thread().name))
        if isinstance(event, TranslateDone) or type(event).__name__ == "JobCrashed":
            self.done.set()


def run(job):
    """Run one job; (events with thread names, records handed to on_record)."""
    log, records = Log(), []
    runner = JobRunner(log, lambda job_id, record: records.append(record))
    try:
        runner.submit(job)
        assert log.done.wait(WAIT_S), f"job did not finish: {log.items}"
    finally:
        runner.shutdown()
    return log.items, records


@pytest.mark.parametrize("target", ["zh", "en"])
def test_translate_stage_passes_the_target(target):
    out = translate_stage(STAGE, ScriptedTranslator(), target)
    assert out.popup == Done("你好", f"{target}:T(你好)")
    assert out.clipboard == ClipboardText(f"{target}:T(你好)")


def test_translate_stage_without_target_follows_the_translator():
    assert translate_stage(STAGE, ScriptedTranslator()).popup == Done("你好", "T(你好)")


def test_translate_job_passes_the_target():
    items, records = run(translate_job(PNG, deps("原文"), ScriptedTranslator(), "zh"))
    done = items[-1][0]
    assert done.outcome.popup == Done("原文", "zh:T(原文)")
    assert records[0].translation == "zh:T(原文)"


@pytest.mark.parametrize("target", [None, "zh", "en"])
def test_text_job_translates_the_text_as_typed(target):
    text = "  改过的原文\n第二行 "
    items, records = run(text_translate_job(text, ScriptedTranslator(), target))
    (started, started_on), (done, done_on) = items
    assert isinstance(started, TranslateStarted)
    assert started.stage.text == text
    assert started_on == "snapocr-jobs"
    assert isinstance(done, TranslateDone)
    assert done_on == "snapocr-translate"
    assert done.job_id == started.job_id
    expected = f"T({text})" if target is None else f"{target}:T({text})"
    assert done.outcome.popup == Done(text, expected)
    assert done.outcome.clipboard == ClipboardText(expected)
    assert records == []


def test_text_job_failure_leaves_the_clipboard():
    err = TranslationError(TranslationErrorKind.UNREACHABLE, base_url="http://127.0.0.1:11434", model="m")
    items, records = run(text_translate_job("Hello", ScriptedTranslator(err), None))
    done = items[-1][0]
    assert done.outcome.clipboard == NoClipboardChange()
    assert isinstance(done.outcome.popup, Failed)
    assert done.outcome.popup.source == "Hello"
    assert done.outcome.record is None
    assert records == []


def test_text_job_with_nothing_to_translate():
    items, _ = run(text_translate_job("123", ScriptedTranslator(TranslationResult("123", None, True)), None))
    done = items[-1][0]
    assert done.outcome.clipboard == NoClipboardChange()
    assert done.outcome.popup == Failed("123", "没有可翻译的文字")


def test_screenshot_translation_still_keeps_its_record():
    items, records = run(translate_job(PNG, deps("原文"), ScriptedTranslator()))
    assert items[-1][0].outcome.record is not None
    assert [r.png for r in records] == [PNG]
