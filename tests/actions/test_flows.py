"""M2 WI-9: capture, OCR and translate flows (PRD F7-1 to F7-6, F8-4; plan A1 to A4).

Pinned here:
- ``HistoryRecord.raw`` is the layout-only text without replacements (A1);
  ``text`` is what goes to the clipboard.
- ``HistoryRecord.error`` is ``str(err)`` for OCR errors, the popup message for
  translation errors and for "nothing to translate"; ``None`` otherwise.
- An empty OCR result records ``raw == text == ""`` with no error.
- The capture notice is ``Notice("已复制截图", "")``; capture keeps no record.
- Privacy (moved here from WI-8): with a unique marker in the OCR text, no
  notice, no popup message and no recorded error contains the marker.
"""

import dataclasses
import logging
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from snapocr.actions.flows import (
    FlowDeps,
    capture_flow,
    code_ocr_flow,
    ocr_flow,
    table_ocr_flow,
    translate_ocr_stage,
    translate_stage,
)
from snapocr.actions.messages import (
    NOTHING_TO_TRANSLATE,
    code_ok_notice,
    table_ok_notice,
    engine_failed_notice,
    ocr_empty_notice,
    ocr_failed_notice,
    ocr_ok_notice,
    translation_error_text,
)
from snapocr.actions.outcomes import (
    ClipboardPng,
    ClipboardTable,
    ClipboardText,
    Done,
    Failed,
    HistoryRecord,
    NoClipboardChange,
    Notice,
    OcrStage,
    Outcome,
    TranslateOutcome,
)
from snapocr.app import DEFAULT_LOG_DIR, LOG_FILE_NAME
from snapocr.engines.config import OcrEngineConfig
from snapocr.engines.errors import EngineLoadError, EngineRuntimeError, InvalidImageError, InvalidImageReason
from snapocr.engines.holder import EngineHolder
from snapocr.engines.rapidocr_engine import RapidOcrEngine
from snapocr.engines.types import OcrResult
from snapocr.postprocess import PostprocessOptions, Replacements, postprocess
from snapocr.translators.errors import TranslationError, TranslationErrorKind
from snapocr.translators.types import TranslationResult
from support.fake_actions import ScriptedTranslator, holder_for
from support.pp_strategies import rect

PNG = b"\x89PNG\r\n\x1a\nfake"
LAYOUT_ONLY = PostprocessOptions(False, False, False)
TABLE = Replacements.from_mapping({"0CR": "OCR"})
RESULT = OcrResult((
    rect("使用0CR截图识别，", 0, 0, 200, 20),
    rect("自动复制到剪贴板。", 0, 30, 180, 50),
    rect("Hello World", 0, 90, 120, 110),
))
EMPTY_RESULTS = [OcrResult(()), OcrResult((rect("   ", 0, 0, 50, 20),))]
LOAD_ERROR = EngineLoadError(["D:/m/det.onnx"], "reinstall rapidocr")
RECOGNIZE_ERRORS = [EngineRuntimeError("engine crashed"), InvalidImageError(InvalidImageReason.NOT_PNG)]


def deps(behaviour=RESULT, *, load_error=None, options=None, replacements=TABLE):
    return FlowDeps(holder_for(behaviour, load_error=load_error), options or PostprocessOptions(), replacements)


def tr_error(kind):
    return TranslationError(kind, base_url="http://127.0.0.1:11434", model="hy-mt2:7b", detail="fixed phrase")


# --- capture ---------------------------------------------------------------------


def test_capture_flow():
    assert capture_flow(PNG) == Outcome(ClipboardPng(PNG), Notice("已复制截图", ""), None)


# --- OCR -------------------------------------------------------------------------


def test_ocr_success():
    expected = postprocess(RESULT, PostprocessOptions(), TABLE)
    raw = postprocess(RESULT, LAYOUT_ONLY)
    assert "OCR" in expected and "0CR" in raw  # replacements apply to text, not raw
    assert ocr_flow(PNG, deps()) == Outcome(
        ClipboardText(expected), ocr_ok_notice(expected), HistoryRecord(PNG, raw, expected)
    )


def test_ocr_options_respected():
    options = PostprocessOptions(paragraphs=True, spacing=False, punctuation=False)
    out = ocr_flow(PNG, deps(options=options, replacements=Replacements.EMPTY))
    assert out.clipboard == ClipboardText(postprocess(RESULT, options))


@pytest.mark.parametrize("result", EMPTY_RESULTS)
def test_ocr_empty(result):
    assert ocr_flow(PNG, deps(result)) == Outcome(NoClipboardChange(), ocr_empty_notice(), HistoryRecord(PNG, "", ""))


def test_ocr_engine_load_error():
    out = ocr_flow(PNG, deps(load_error=LOAD_ERROR))
    assert out == Outcome(NoClipboardChange(), engine_failed_notice(LOAD_ERROR, DEFAULT_LOG_DIR / LOG_FILE_NAME),
                          HistoryRecord(PNG, "", "", error=str(LOAD_ERROR)))


def test_ocr_factory_crash_becomes_load_error():
    # M3 WI-9: the cause is in the record and the log, no longer in the notice.
    out = ocr_flow(PNG, deps(load_error=RuntimeError("dll missing")))
    assert out.clipboard == NoClipboardChange()
    assert out.notice.title == "OCR 引擎加载失败"
    assert out.notice.body.startswith("OCR 引擎没能初始化\n")
    assert "dll missing" in out.record.error


def test_engine_load_error_notice_names_the_log_file_of_the_deps():
    log_file = Path("E:/elsewhere/snap.log")
    d = dataclasses.replace(deps(load_error=LOAD_ERROR), log_file=log_file)
    assert ocr_flow(PNG, d).notice == engine_failed_notice(LOAD_ERROR, log_file)


@pytest.mark.parametrize("run", ["ocr", "translate"])
def test_engine_load_error_is_logged_in_full(caplog, run):
    # M3 WI-9 (F7-4): the fix command and every model path go to the log.
    err = EngineLoadError(["D:/m/det.onnx", "D:/m/rec.onnx"], "run `uv pip install --reinstall rapidocr`",
                          detail="OSError: file not found")
    with caplog.at_level(logging.WARNING, logger="snapocr.actions.flows"):
        if run == "ocr":
            ocr_flow(PNG, deps(load_error=err))
        else:
            translate_ocr_stage(PNG, deps(load_error=err))
    records = [r for r in caplog.records if r.name == "snapocr.actions.flows"]
    assert [(r.levelno, r.getMessage()) for r in records] == [(logging.WARNING, f"OCR engine failed to load: {err}")]


def test_successful_ocr_logs_nothing(caplog):
    with caplog.at_level(logging.DEBUG, logger="snapocr.actions.flows"):
        ocr_flow(PNG, deps())
    assert [r for r in caplog.records if r.name == "snapocr.actions.flows"] == []


@pytest.mark.parametrize("err", RECOGNIZE_ERRORS, ids=["runtime", "invalid-image"])
def test_ocr_recognize_error(err):
    assert ocr_flow(PNG, deps(err)) == Outcome(NoClipboardChange(), ocr_failed_notice(err),
                                               HistoryRecord(PNG, "", "", error=str(err)))


def test_ocr_unexpected_exception_propagates():
    # Not an OcrError: the runner reports it as a crashed job (WI-11).
    with pytest.raises(ZeroDivisionError):
        ocr_flow(PNG, deps(ZeroDivisionError()))


def test_ocr_real_engine_missing_models():
    # F7-4 real path: RapidOcrEngine checks the files before importing rapidocr.
    missing = Path("snapocr-missing-models-wi9")
    holder = EngineHolder(lambda: RapidOcrEngine(OcrEngineConfig(model_dir=missing)).load())
    out = ocr_flow(PNG, FlowDeps(holder, PostprocessOptions(), Replacements.EMPTY))
    assert out.clipboard == NoClipboardChange()
    assert out.notice.title == "OCR 引擎加载失败"
    # M3 WI-9: the notice names the file; the paths and the fix command are in the record (and the log).
    assert out.notice.body.startswith("模型文件缺失或损坏：PP-OCRv6_det_small.onnx 等 3 个\n")
    assert "uv pip install" not in out.notice.body
    assert str(missing / "PP-OCRv6_det_small.onnx") in out.record.error
    assert "uv pip install" in out.record.error


# --- translate -------------------------------------------------------------------


def test_translate_ocr_stage_success():
    text = postprocess(RESULT, PostprocessOptions(), TABLE)
    assert translate_ocr_stage(PNG, deps()) == OcrStage(PNG, postprocess(RESULT, LAYOUT_ONLY), text)


@pytest.mark.parametrize(
    "make", [lambda: deps(EMPTY_RESULTS[0]), lambda: deps(EMPTY_RESULTS[1]), lambda: deps(load_error=LOAD_ERROR),
             lambda: deps(RECOGNIZE_ERRORS[0]), lambda: deps(RECOGNIZE_ERRORS[1])],
    ids=["empty", "blank", "load", "runtime", "invalid-image"],
)
def test_translate_ocr_stage_stops_like_ocr_flow(make):
    # A4: empty or failed OCR ends here with the same outcome as the OCR action.
    assert translate_ocr_stage(PNG, make()) == ocr_flow(PNG, make())


STAGE = OcrStage(PNG, "raw text", "使用 OCR 截图")


def test_translate_success_translates_postprocessed_text():
    out = translate_stage(STAGE, ScriptedTranslator())
    assert out == TranslateOutcome(
        ClipboardText("T(使用 OCR 截图)"),
        Done("使用 OCR 截图", "T(使用 OCR 截图)"),
        HistoryRecord(PNG, "raw text", "使用 OCR 截图", translation="T(使用 OCR 截图)"),
    )


def test_translate_skipped():
    out = translate_stage(STAGE, ScriptedTranslator(TranslationResult("123", None, True)))
    assert out == TranslateOutcome(
        NoClipboardChange(),
        Failed("使用 OCR 截图", NOTHING_TO_TRANSLATE),
        HistoryRecord(PNG, "raw text", "使用 OCR 截图", error=NOTHING_TO_TRANSLATE),
    )


@pytest.mark.parametrize("kind", list(TranslationErrorKind))
def test_translate_error_kinds(kind):
    err = tr_error(kind)
    out = translate_stage(STAGE, ScriptedTranslator(err))
    message = translation_error_text(err)
    assert out == TranslateOutcome(
        NoClipboardChange(),
        Failed("使用 OCR 截图", message),
        HistoryRecord(PNG, "raw text", "使用 OCR 截图", error=message),
    )


def test_translate_unexpected_exception_propagates():
    with pytest.raises(KeyError):
        translate_stage(STAGE, ScriptedTranslator(KeyError("x")))


# --- properties ------------------------------------------------------------------

MARKER = "⟦M7⟧"
block_texts = st.sampled_from(["使用0CR截图", "Hello", f"含{MARKER}标记", "   ", "，。", "123"])


@st.composite
def results(draw):
    texts = draw(st.lists(block_texts, max_size=4))
    return OcrResult(tuple(rect(t, 0, 30 * i, 100, 30 * i + 20) for i, t in enumerate(texts)))


engine_cases = st.one_of(
    st.tuples(results(), st.none()),
    st.tuples(st.sampled_from(RECOGNIZE_ERRORS), st.none()),
    st.tuples(st.just(RESULT), st.sampled_from([LOAD_ERROR, RuntimeError("boom")])),
)
translator_cases = st.one_of(
    st.just("echo"),
    st.just(TranslationResult("1", None, True)),
    st.sampled_from(list(TranslationErrorKind)).map(tr_error),
)


def run_translate(engine_case, translator_case):
    """The translate action end to end: records produced, popup (or None), outcome."""
    stage = translate_ocr_stage(PNG, deps(engine_case[0], load_error=engine_case[1]))
    if isinstance(stage, Outcome):
        return [stage.record], None, stage
    out = translate_stage(stage, ScriptedTranslator(translator_case))
    return [out.record], out.popup, out


@given(engine_cases, translator_cases)
def test_exactly_one_record_per_flow(engine_case, translator_case):
    out = ocr_flow(PNG, deps(engine_case[0], load_error=engine_case[1]))
    assert isinstance(out.record, HistoryRecord) and out.record.png == PNG
    records, _, _ = run_translate(engine_case, translator_case)
    assert len(records) == 1 and isinstance(records[0], HistoryRecord) and records[0].png == PNG


@given(engine_cases, translator_cases)
def test_clipboard_untouched_unless_success(engine_case, translator_case):
    out = ocr_flow(PNG, deps(engine_case[0], load_error=engine_case[1]))
    if out.record.error is not None or not out.record.text:
        assert out.clipboard == NoClipboardChange()
    else:
        assert out.clipboard == ClipboardText(out.record.text)
    _, popup, t_out = run_translate(engine_case, translator_case)
    if isinstance(popup, Done):
        assert t_out.clipboard == ClipboardText(popup.translation)
    else:
        assert t_out.clipboard == NoClipboardChange()


@given(results(), st.lists(st.sampled_from(["", "  ", "\t"]), min_size=1, max_size=3))
def test_empty_blocks_do_not_change_clipboard(result, blanks):
    extra = tuple(rect(b, 300, 300 + 30 * i, 350, 320 + 30 * i) for i, b in enumerate(blanks))
    a = ocr_flow(PNG, deps(result))
    b = ocr_flow(PNG, deps(OcrResult(result.blocks + extra)))
    assert a.clipboard == b.clipboard


@given(engine_cases, translator_cases)
def test_errors_never_carry_ocr_text(engine_case, translator_case):
    out = ocr_flow(PNG, deps(engine_case[0], load_error=engine_case[1]))
    if out.record.error is not None or out.clipboard == NoClipboardChange():
        assert MARKER not in out.notice.title + out.notice.body
    if out.record.error is not None:
        assert MARKER not in out.record.error
    records, popup, t_out = run_translate(engine_case, translator_case)
    if isinstance(popup, Failed):
        assert MARKER not in popup.message
    if records[0].error is not None:
        assert MARKER not in records[0].error


# --- M3 WI-11: show_text (F7-2) -------------------------------------------------------


def test_ocr_success_without_text_in_the_notice():
    d = dataclasses.replace(deps(), show_text=False)
    out = ocr_flow(PNG, d)
    expected = postprocess(RESULT, PostprocessOptions(), TABLE)
    assert out == Outcome(ClipboardText(expected), ocr_ok_notice(expected, show_text=False),
                          HistoryRecord(PNG, postprocess(RESULT, LAYOUT_ONLY), expected))
    assert out.notice.body.startswith("共 ")


def test_flow_deps_show_text_defaults_to_true():
    assert deps().show_text is True


# --- M3 WI-14: code OCR (PRD F13-1) ---------------------------------------------
#
# Pinned here: the clipboard text is ``code_text`` (F13-2 to F13-4: indentation
# kept, no prose rules, no replacement table); the record's ``raw`` is the
# layout-only text as for OCR (plan A1); empty and failed runs end exactly like
# the OCR action.

CODE_RESULT = OcrResult((
    rect("def f():", 0, 0, 80, 20),
    rect("x = 0CR", 40, 30, 110, 50),
    rect("s = '中文abc'", 40, 60, 150, 80),
))
CODE = "def f():\n    x = 0CR\n    s = '中文abc'"


def test_code_ocr_flow_copies_the_indented_code():
    d = deps(CODE_RESULT)
    out = code_ocr_flow(PNG, d)
    assert out == Outcome(
        ClipboardText(CODE),
        code_ok_notice(CODE),
        HistoryRecord(PNG, postprocess(CODE_RESULT, LAYOUT_ONLY), CODE),
    )
    assert out.notice.title == "已复制代码"


def test_code_ocr_flow_notice_without_text():
    d = dataclasses.replace(deps(CODE_RESULT), show_text=False)
    assert code_ocr_flow(PNG, d).notice == Notice("已复制代码", "共 21 个字")


@pytest.mark.parametrize("make_deps", [
    lambda: deps(OcrResult(())),
    lambda: deps(load_error=LOAD_ERROR),
    lambda: deps(EngineRuntimeError("engine crashed")),
], ids=["empty", "load-error", "recognize-error"])
def test_code_ocr_flow_failures_end_like_ocr(make_deps):
    d = make_deps()
    out = code_ocr_flow(PNG, d)
    assert out == ocr_flow(PNG, make_deps())
    assert out.clipboard == NoClipboardChange()


# --- M4 WI-15: table OCR (PRD F16-1, F16-2; plan D23) ---------------------------------
#
# Pinned here: the clipboard holds ``to_markdown`` and ``to_html`` of
# ``table_cells``; the record's ``text`` is the Markdown, ``raw`` the
# layout-only text; the notice gives rows x columns; a result that leaves no
# cell (nothing recognized, or only spreadsheet letters) and failed runs end
# exactly like the OCR action.

TABLE_RESULT = OcrResult((
    rect("Name", 0, 0, 60, 20), rect("Qty", 200, 0, 240, 20),
    rect("0CR", 0, 30, 40, 50), rect("3", 220, 30, 230, 50),
    rect("Pear", 0, 60, 50, 80), rect("12", 215, 60, 235, 80),
))
TABLE_MD = "| Name | Qty |\n| --- | --- |\n| 0CR | 3 |\n| Pear | 12 |"  # no replacement table
TABLE_HTML = (
    "<table>\n<tr><td>Name</td><td>Qty</td></tr>\n<tr><td>0CR</td><td>3</td></tr>\n"
    "<tr><td>Pear</td><td>12</td></tr>\n</table>"
)


def test_table_ocr_flow_copies_markdown_and_html():
    out = table_ocr_flow(PNG, deps(TABLE_RESULT))
    assert out == Outcome(
        ClipboardTable(TABLE_MD, TABLE_HTML),
        table_ok_notice(3, 2),
        HistoryRecord(PNG, postprocess(TABLE_RESULT, LAYOUT_ONLY), TABLE_MD),
    )
    assert out.notice == Notice("已复制表格", "3 行 × 2 列")


def test_table_ocr_flow_with_only_column_letters_is_empty():
    letters = OcrResult((rect("A", 100, 0, 120, 20), rect("B", 200, 0, 220, 20)))
    out = table_ocr_flow(PNG, deps(letters))
    assert out == Outcome(NoClipboardChange(), ocr_empty_notice(),
                          HistoryRecord(PNG, postprocess(letters, LAYOUT_ONLY), ""))


@pytest.mark.parametrize("make_deps", [
    lambda: deps(OcrResult(())),
    lambda: deps(load_error=LOAD_ERROR),
    lambda: deps(EngineRuntimeError("engine crashed")),
], ids=["empty", "load-error", "recognize-error"])
def test_table_ocr_flow_failures_end_like_ocr(make_deps):
    out = table_ocr_flow(PNG, make_deps())
    assert out == ocr_flow(PNG, make_deps())
    assert out.clipboard == NoClipboardChange()
