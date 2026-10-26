"""M2 WI-8: outcome types and user-facing texts (PRD F5-3, F7-2 to F7-4, F8-4, F9-3).

Pinned here:
- ``Notice`` keeps at most 240 code points of ``body``; a longer body becomes
  its first 239 code points plus "…".
- The engine-load notice puts the fix first and the model paths after it, so a
  cut (long paths) loses paths before the fix; the full text goes to the log.
- The privacy property (error notices never contain OCR text) is tested in
  WI-9, where the text and the errors meet; these builders never see the text.
"""

from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from snapocr.actions.messages import (
    COMMAND_LABELS,
    config_issues_notice,
    engine_failed_notice,
    hotkey_failed_notice,
    ocr_empty_notice,
    ocr_failed_notice,
    ocr_ok_notice,
    preview,
    translation_error_text,
)
from snapocr.actions.outcomes import NOTICE_BODY_MAX, ClipboardPng, ClipboardText, NoClipboardChange, Notice
from snapocr.commands import Command
from snapocr.config.schema import ConfigIssue
from snapocr.engines.errors import EngineLoadError, EngineRuntimeError, InvalidImageError, InvalidImageReason
from snapocr.hotkeys import HotkeyFailure
from snapocr.translators.errors import TranslationError, TranslationErrorKind

CFG = Path("D:/LLM/workspace/snapocr/config.local.toml")


# --- outcome types ---------------------------------------------------------------


def test_notice_body_cut_at_240():
    assert NOTICE_BODY_MAX == 240
    assert Notice("t", "x" * 240).body == "x" * 240
    assert Notice("t", "x" * 241).body == "x" * 239 + "…"
    assert Notice("t", "😀" * 300).body == "😀" * 239 + "…"
    assert Notice("t", "").body == ""


def test_clipboard_values():
    assert ClipboardText("a") == ClipboardText("a")
    assert ClipboardPng(b"\x89PNG") != ClipboardPng(b"")
    assert NoClipboardChange() == NoClipboardChange()


@pytest.mark.parametrize("cls,args", [(Notice, (1, "b")), (Notice, ("a", None)), (ClipboardText, (b"x",)),
                                      (ClipboardPng, ("x",)), (ClipboardPng, (bytearray(b"x"),))])
def test_types_validated(cls, args):
    with pytest.raises(TypeError):
        cls(*args)


# --- preview ---------------------------------------------------------------------


def test_preview_examples():
    forty = "一二三四五六七八九十" * 4
    assert preview(forty) == forty[:30] + "…"
    assert preview(forty[:29]) == forty[:29]
    assert preview(forty[:30]) == forty[:30]
    assert preview(forty[:31]) == forty[:30] + "…"
    assert preview("") == ""
    assert preview(" \n\t ") == ""
    assert preview("  第一行\n\n第二行\t end  ") == "第一行 第二行 end"
    assert preview("😀" * 31) == "😀" * 30 + "…"
    assert preview("abcdef", n=3) == "abc…"


def normalize(s):
    return " ".join(s.split())


@given(st.text(), st.integers(1, 60))
def test_preview_is_prefix_of_normalized(s, n):
    p = preview(s, n)
    core = p[:-1] if p.endswith("…") and len(normalize(s)) > n else p
    assert normalize(s).startswith(core)
    assert len(p) <= n + 1
    assert (len(normalize(s)) > n) == (p != normalize(s))


# --- notices ---------------------------------------------------------------------


def test_ocr_ok_notice():
    n = ocr_ok_notice("使用 Python3 截图识别，\n自动复制到剪贴板。还有更多的文字在后面")
    assert n.title == "已复制 OCR 文本"
    assert n.body == preview("使用 Python3 截图识别，\n自动复制到剪贴板。还有更多的文字在后面")


def test_ocr_empty_notice():
    assert ocr_empty_notice().title == "未识别到文字"
    assert "剪贴板" in ocr_empty_notice().body


def test_engine_failed_notice_names_paths_and_fix():
    err = EngineLoadError(["D:/m/PP-OCRv6_det_small.onnx", "D:/m/PP-OCRv6_rec_small.onnx"], "reinstall rapidocr")
    n = engine_failed_notice(err)
    assert "OCR" in n.title
    assert "D:/m/PP-OCRv6_det_small.onnx" in n.body and "D:/m/PP-OCRv6_rec_small.onnx" in n.body
    assert "reinstall rapidocr" in n.body
    assert n.body.index("reinstall rapidocr") < n.body.index("D:/m/")


def test_engine_failed_notice_with_detail():
    n = engine_failed_notice(EngineLoadError([], "fix it", detail="onnx session failed"))
    assert "onnx session failed" in n.body and "fix it" in n.body


def test_engine_failed_notice_long_keeps_fix():
    paths = [f"D:/very/long/path/{'x' * 80}/model{i}.onnx" for i in range(3)]
    hint = "run `uv pip install --reinstall rapidocr==3.10.0`, or set `model_dir` in the config"
    n = engine_failed_notice(EngineLoadError(paths, hint))
    assert len(n.body) == NOTICE_BODY_MAX
    assert hint in n.body


def test_ocr_failed_notice():
    n = ocr_failed_notice(EngineRuntimeError("engine crashed"))
    assert n.title == "OCR 失败"
    assert "engine crashed" in n.body
    assert "剪贴板" in n.body
    m = ocr_failed_notice(InvalidImageError(InvalidImageReason.EMPTY))
    assert "EMPTY" in m.body


def test_translation_error_text():
    err = TranslationError(TranslationErrorKind.TIMEOUT, base_url="http://127.0.0.1:11434", model="hy-mt2:7b")
    text = translation_error_text(err)
    assert text.startswith("翻译失败")
    assert str(err) in text


def test_command_labels():
    assert COMMAND_LABELS == {
        Command.CAPTURE: "截图", Command.OCR: "OCR", Command.TRANSLATE: "翻译",
        Command.LAST_RESULT: "上次结果", Command.OPEN_CONFIG: "打开配置文件", Command.QUIT: "退出",
    }


def test_hotkey_failed_notice_names_hotkey_and_action():
    n = hotkey_failed_notice([HotkeyFailure(Command.OCR, "Alt+2", 1409),
                              HotkeyFailure(Command.TRANSLATE, "Alt+3", 5)])
    assert n.title == "有 2 个热键注册失败"
    lines = n.body.split("\n")
    assert lines[0] == "Alt+2（OCR）：已被其他软件占用"
    assert lines[1] == "Alt+3（翻译）：注册失败，错误码 5"
    assert "其余热键照常工作" in n.body
    assert "config.local.toml" in n.body


def test_hotkey_failed_notice_one():
    n = hotkey_failed_notice([HotkeyFailure(Command.CAPTURE, "Alt+1", 1409)])
    assert n.title == "有 1 个热键注册失败"
    assert n.body.startswith("Alt+1（截图）：已被其他软件占用")


def test_config_issues_notice():
    issues = [ConfigIssue(CFG, "translator.timout_s", "unknown key, ignored; did you mean 'timeout_s'?"),
              ConfigIssue(CFG, "", "TOML syntax error: x (at line 3, column 1); using defaults")]
    n = config_issues_notice(issues)
    assert n.title == "配置文件有 2 个问题"
    assert n.body.split("\n")[:2] == [str(issues[0]), str(issues[1])]


@pytest.mark.parametrize("fn", [hotkey_failed_notice, config_issues_notice])
def test_empty_lists_rejected(fn):
    with pytest.raises(ValueError):
        fn([])


# --- properties ------------------------------------------------------------------

kinds = st.sampled_from(list(TranslationErrorKind))
texts = st.text(max_size=400)


@given(texts, texts, st.lists(texts, max_size=4), st.lists(
    st.builds(HotkeyFailure, st.sampled_from(list(Command)), texts, st.integers(0, 2**31)), min_size=1, max_size=6),
    st.lists(st.builds(ConfigIssue, st.just(CFG), texts, texts), min_size=1, max_size=8))
def test_every_notice_body_bounded(text, hint, paths, failures, issues):
    notices = [
        ocr_ok_notice(text), ocr_empty_notice(), engine_failed_notice(EngineLoadError(paths, hint, detail=text)),
        ocr_failed_notice(EngineRuntimeError(text)), hotkey_failed_notice(failures), config_issues_notice(issues),
    ]
    for n in notices:
        assert isinstance(n, Notice)
        assert len(n.body) <= NOTICE_BODY_MAX
        assert n.title and len(n.title) <= 40


def test_engine_failed_notice_first_path_always_whole():
    # Found in WI-9: the real fix hint is ~200 code points; the path must still show.
    hint = "missing, empty or not a file; run `" + "u" * 220 + "`"
    n = engine_failed_notice(EngineLoadError(["models/PP-OCRv6_det_small.onnx", "models/rec.onnx"], hint))
    fix_line, paths_line = n.body.split("\n")[:2]
    assert fix_line.startswith("修复：missing, empty or not a file") and fix_line.endswith("…")
    assert paths_line.startswith("模型文件：models/PP-OCRv6_det_small.onnx")
    assert len(n.body) <= NOTICE_BODY_MAX


def test_engine_failed_notice_very_long_first_path_keeps_some_fix():
    n = engine_failed_notice(EngineLoadError(["D:/" + "p" * 400], "reinstall rapidocr " * 10))
    assert n.body.startswith("修复：reinstall rapidocr")
    assert len(n.body) == NOTICE_BODY_MAX


# --- WI-17: controller notices --------------------------------------------------------

from snapocr.actions.messages import (  # noqa: E402
    capture_failed_notice,
    config_opened_notice,
    job_crashed_notice,
    job_crashed_text,
    open_config_failed_notice,
)


def test_capture_failed_notice():
    n = capture_failed_notice("BitBlt failed")
    assert n.title == "截图失败"
    assert n.body == "BitBlt failed\n剪贴板没有改动。"


def test_job_crashed_texts():
    assert job_crashed_text("RuntimeError") == "内部错误（RuntimeError），详情见日志"
    n = job_crashed_notice("RuntimeError")
    assert n.title == "操作失败"
    assert n.body == "内部错误（RuntimeError），详情见日志。剪贴板没有改动。"


def test_config_opened_notice():
    assert config_opened_notice() == Notice("已打开配置文件", "修改后重启 snapocr 生效。")


def test_open_config_failed_notice():
    n = open_config_failed_notice(CFG, "no application is associated")
    assert n.title == "无法打开配置文件"
    assert n.body == f"{CFG}\nno application is associated"


@given(texts)
def test_new_notice_bodies_bounded(text):
    for n in (capture_failed_notice(text), job_crashed_notice(text), open_config_failed_notice(text, text)):
        assert len(n.body) <= NOTICE_BODY_MAX
