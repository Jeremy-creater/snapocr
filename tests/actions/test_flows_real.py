"""M2 WI-12: the action flows on their real paths (pairs with the fakes in WI-9 / WI-11).

- ``engine`` lane: the real RapidOCR engine behind a real ``EngineHolder``
  recognizes the committed samples through ``ocr_flow`` / the translate job's
  OCR half. Missing models or fixtures FAIL (``loaded_engine`` / ``_read``).
- ``integration`` lane (manual): ``translate_stage`` against real Ollama
  ``hy-mt2:7b`` on 127.0.0.1. ``require_ollama`` FAILS when it is down.

No law of their own; the expected strings are the ones pinned by F2 WI-8.
"""

import dataclasses
import threading
from pathlib import Path

import pytest

from snapocr.actions.flows import FlowDeps, ocr_flow, translate_ocr_stage, translate_stage
from snapocr.actions.history import ResultHistory
from snapocr.actions.outcomes import ClipboardText, Done, Failed, NoClipboardChange, OcrStage
from snapocr.actions.runner import JobRunner, OcrDone, TranslateDone, TranslateStarted, ocr_job, translate_job
from snapocr.engines.holder import EngineHolder
from snapocr.postprocess import PostprocessOptions, Replacements
from snapocr.translators import OpenAICompatTranslator
from snapocr.translators.config import TranslatorConfig
from snapocr.translators.direction import detect_target_lang
from support.cer_check import assert_cer_within
from support.fake_actions import ScriptedTranslator

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
# Same literal as tests/engines/test_postprocess_real.MIXED_EXPECTED (F2 WI-8).
MIXED_EXPECTED = "使用 Python3 截图识别，自动复制到剪贴板。\nHello World, snapocr 123 test."
CER_LIMIT = 0.02
NO_TABLE = Replacements.from_mapping({})


def _read(path: Path) -> bytes:
    if not path.is_file():
        pytest.fail(f"missing test fixture {path}; regenerate with tests/fixtures/make_fixtures.ps1")
    return path.read_bytes()


def _ref_lines(name: str) -> list[str]:
    return [line for line in _read(FIXTURES / f"{name}.txt").decode("utf-8").splitlines() if line.strip()]


@pytest.fixture(scope="module")
def real_deps(loaded_engine):
    def make(table: Replacements = NO_TABLE) -> FlowDeps:
        return FlowDeps(EngineHolder(lambda: loaded_engine), PostprocessOptions(), table)

    return make


def _run_jobs(jobs, history=None, terminal=2):
    """Run jobs on a real JobRunner and return its events once ``terminal`` jobs have ended."""
    events, done = [], threading.Event()

    def on_event(event):
        events.append(event)
        if sum(isinstance(e, (OcrDone, TranslateDone)) for e in events) >= terminal:
            done.set()

    runner = JobRunner(on_event, history if history is not None else ResultHistory())
    try:
        for job in jobs:
            runner.submit(job)
        assert done.wait(60), events
    finally:
        runner.shutdown()
    return events


# --- engine lane -------------------------------------------------------------


@pytest.mark.engine
def test_ocr_flow_real_engine_mixed_exact(real_deps):
    png = _read(FIXTURES / "mixed.png")
    outcome = ocr_flow(png, real_deps())
    assert outcome.clipboard == ClipboardText(MIXED_EXPECTED)
    assert outcome.notice.body == MIXED_EXPECTED.replace("\n", " ")[:30] + "…"
    record = outcome.record
    assert record.png == png
    assert record.text == MIXED_EXPECTED
    assert record.error is None and record.translation is None
    assert len(record.raw.split("\n")) == len(_ref_lines("mixed"))


@pytest.mark.engine
@pytest.mark.parametrize("name", ["zh", "en", "mixed"])
def test_ocr_flow_real_engine_lines_and_cer(real_deps, name):
    outcome = ocr_flow(_read(FIXTURES / f"{name}.png"), real_deps())
    ref = _ref_lines(name)
    assert isinstance(outcome.clipboard, ClipboardText)
    out_lines = outcome.clipboard.text.split("\n")
    assert len(out_lines) == len(ref), out_lines
    assert len(outcome.record.raw.split("\n")) == len(ref)
    for i, (out, expected) in enumerate(zip(out_lines, ref)):
        assert_cer_within(out, expected, CER_LIMIT, f"{name} line {i + 1}")


@pytest.mark.engine
def test_ocr_flow_real_engine_applies_replacements_but_raw_does_not(real_deps):
    table = Replacements.from_mapping({"snapocr": "SnapOCR"})
    outcome = ocr_flow(_read(FIXTURES / "mixed.png"), real_deps(table))
    assert outcome.clipboard == ClipboardText(MIXED_EXPECTED.replace("snapocr", "SnapOCR"))
    assert "snapocr" in outcome.record.raw
    assert "SnapOCR" not in outcome.record.raw


@pytest.mark.engine
def test_ocr_flow_real_engine_blank_image_is_empty(real_deps):
    outcome = ocr_flow(_read(FIXTURES / "blank.png"), real_deps())
    assert outcome.clipboard == NoClipboardChange()
    assert outcome.notice.title == "未识别到文字"
    assert outcome.record.text == "" and outcome.record.error is None


@pytest.mark.engine
def test_translate_job_real_engine_hands_postprocessed_text_to_translator(real_deps):
    """F7-5 / plan A2 on the real OCR path: the runner's TranslateStarted carries the clipboard text."""
    png = _read(FIXTURES / "mixed.png")
    stage = translate_ocr_stage(png, real_deps())
    assert stage == OcrStage(png, stage.raw, MIXED_EXPECTED)

    events = _run_jobs([translate_job(png, real_deps(), ScriptedTranslator())], terminal=1)
    assert [type(e) for e in events] == [TranslateStarted, TranslateDone]
    assert events[0].stage.text == MIXED_EXPECTED
    assert events[1].outcome.popup == Done(MIXED_EXPECTED, f"T({MIXED_EXPECTED})")


@pytest.mark.engine
def test_ocr_flow_real_engine_through_runner_records_history(real_deps):
    history = ResultHistory()
    events = _run_jobs(
        [ocr_job(_read(FIXTURES / "zh.png"), real_deps()), ocr_job(_read(FIXTURES / "blank.png"), real_deps())],
        history,
    )
    assert [type(e) for e in events] == [OcrDone, OcrDone]
    assert isinstance(events[0].outcome.clipboard, ClipboardText)
    assert events[1].outcome.clipboard == NoClipboardChange()
    assert [r.text == "" for r in history.snapshot()] == [True, False]


# --- integration lane (real Ollama) -----------------------------------------

REAL_TR = TranslatorConfig(sampling={"temperature": 0, "seed": 42})
ZH_SOURCE = "今天天气很好，我们去公园散步。"


def _stage(text: str) -> OcrStage:
    return OcrStage(b"\x89PNG\r\n\x1a\nstage", text, text)


@pytest.mark.integration
@pytest.mark.usefixtures("require_ollama", "loopback_guard")
def test_translate_stage_real_ollama():
    outcome = translate_stage(_stage(ZH_SOURCE), OpenAICompatTranslator(REAL_TR))
    assert isinstance(outcome.clipboard, ClipboardText)
    translation = outcome.clipboard.text
    assert translation and translation == translation.strip()
    assert detect_target_lang(translation, 0.3) == "zh"  # English output: it would translate back to zh
    assert "park" in translation.lower()
    assert outcome.popup == Done(ZH_SOURCE, translation)
    assert outcome.record.translation == translation
    assert outcome.record.text == ZH_SOURCE and outcome.record.error is None


@pytest.mark.integration
@pytest.mark.usefixtures("require_ollama", "loopback_guard")
def test_translate_stage_real_ollama_missing_model():
    config = dataclasses.replace(REAL_TR, model="snapocr-no-such-model:0")
    outcome = translate_stage(_stage(ZH_SOURCE), OpenAICompatTranslator(config))
    assert outcome.clipboard == NoClipboardChange()
    assert isinstance(outcome.popup, Failed)
    assert outcome.popup.source == ZH_SOURCE
    assert outcome.popup.message
    assert ZH_SOURCE not in outcome.popup.message
    assert "天气" not in outcome.popup.message
    assert outcome.record.error == outcome.popup.message
    assert outcome.record.translation is None
