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


LOG_FILE = Path("D:/DevLocal/runtime/snapocr/snapocr.log")
REAL_HINT = r"missing, empty or not a file; run `uv pip install --python D:\DevLocal\envs\snapocr\Scripts\python.exe --reinstall rapidocr==3.10.0`, or set `model_dir` in the config to a directory holding the models"


def test_engine_failed_notice_names_the_missing_file_and_the_log():
    # M3 WI-9 (F7-4, PRD 2026-10-27): a short reason and where the full story is.
    err = EngineLoadError(["D:/m/PP-OCRv6_det_small.onnx"], REAL_HINT, detail="file not found")
    n = engine_failed_notice(err, LOG_FILE)
    assert n.title == "OCR 引擎加载失败"
    assert n.body == f"模型文件缺失或损坏：PP-OCRv6_det_small.onnx\n完整原因和修复命令见日志：{LOG_FILE}"


def test_engine_failed_notice_counts_further_files():
    err = EngineLoadError(["D:/m/det.onnx", "D:/m/cls.onnx", "D:/m/rec.onnx"], "reinstall rapidocr")
    first = engine_failed_notice(err, LOG_FILE).body.split("\n")[0]
    assert first == "模型文件缺失或损坏：det.onnx 等 3 个"


def test_engine_failed_notice_without_paths():
    n = engine_failed_notice(EngineLoadError([], "fix it", detail="RuntimeError: dll missing"), LOG_FILE)
    assert n.body == f"OCR 引擎没能初始化\n完整原因和修复命令见日志：{LOG_FILE}"


def test_engine_failed_notice_shortens_a_long_file_name():
    name = "m" * 100 + ".onnx"
    first = engine_failed_notice(EngineLoadError([f"D:/x/{name}"], "h"), LOG_FILE).body.split("\n")[0]
    assert first == "模型文件缺失或损坏：" + name[:59] + "…"


def test_engine_failed_notice_shortens_the_reason_for_a_long_log_path():
    log_file = Path("D:/" + "d" * 190 + "/snapocr.log")
    n = engine_failed_notice(EngineLoadError([f"D:/m/{'n' * 50}.onnx", "D:/m/b.onnx"], "h"), log_file)
    reason, where = n.body.split("\n")
    assert where == f"完整原因和修复命令见日志：{log_file}"
    assert reason.startswith("模型文件缺失或损坏：nnn") and reason.endswith("…")
    assert len(n.body) == NOTICE_BODY_MAX


def test_engine_failed_notice_leaves_out_the_fix_and_the_cause():
    # The fix command (~200 chars) was cut at 240 before; now it lives in the log only.
    n = engine_failed_notice(EngineLoadError(["D:/m/det.onnx"], REAL_HINT, detail="onnx says no"), LOG_FILE)
    assert "uv pip install" not in n.body and "onnx says no" not in n.body and "D:/m/" not in n.body


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
        Command.LAST_RESULT: "上次结果", Command.SETTINGS: "设置…", Command.OPEN_CONFIG: "打开配置文件",
        Command.QUIT: "退出",
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
        ocr_ok_notice(text), ocr_empty_notice(), engine_failed_notice(EngineLoadError(paths, hint, detail=text), LOG_FILE),
        ocr_failed_notice(EngineRuntimeError(text)), hotkey_failed_notice(failures), config_issues_notice(issues),
    ]
    for n in notices:
        assert isinstance(n, Notice)
        assert len(n.body) <= NOTICE_BODY_MAX
        assert n.title and len(n.title) <= 40


@given(texts, texts, st.lists(texts, max_size=4), st.text(min_size=1, max_size=150))
def test_engine_failed_notice_always_shows_the_whole_log_path(hint, detail, paths, log_name):
    log_file = Path("D:/DevLocal/runtime") / log_name.replace("/", "_").replace("\\", "_")
    n = engine_failed_notice(EngineLoadError(paths, hint, detail=detail), log_file)
    assert n.body.endswith(f"完整原因和修复命令见日志：{log_file}")
    assert len(n.body) <= NOTICE_BODY_MAX


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


# --- M3 WI-6: settings window texts (PRD F11-3) ---------------------------------------------

from snapocr.actions.messages import (  # noqa: E402
    autostart_failed_text,
    hotkey_failure_line,
    settings_problem_text,
    settings_saved_notice,
)
from snapocr.config.settings import BadModel, BadTargetLang, DuplicateHotkey  # noqa: E402
from snapocr.hotkeys import parse_hotkey  # noqa: E402


def test_hotkey_failed_notice_points_to_settings():
    n = hotkey_failed_notice([HotkeyFailure(Command.OCR, "Alt+2", 1409)])
    assert n.body.split("\n")[-1] == "其余热键照常工作。可以在托盘菜单的“设置…”里换一个组合（或改 config.local.toml 的 [hotkeys]）。"


def test_hotkey_failure_line():
    assert hotkey_failure_line(HotkeyFailure(Command.CAPTURE, "Ctrl+Q", 1409)) == "Ctrl+Q（截图）：已被其他软件占用"
    assert hotkey_failure_line(HotkeyFailure(Command.TRANSLATE, "Ctrl+Q", 87)) == "Ctrl+Q（翻译）：注册失败，错误码 87"


def test_settings_problem_texts():
    dup = DuplicateHotkey(Command.CAPTURE, Command.LAST_RESULT, parse_hotkey("alt+1"))
    assert settings_problem_text(dup) == "「截图」和「上次结果」用了同一个热键 Alt+1。"
    assert settings_problem_text(BadModel("must be a non-empty str")) == "模型名不能用：must be a non-empty str"
    assert settings_problem_text(BadTargetLang("fr")) == "目标语言只能是自动、中文或英文。"


def test_autostart_failed_text():
    assert autostart_failed_text(PermissionError(13, "Access is denied")) == "无法设置开机自启动：Access is denied"
    assert autostart_failed_text(OSError("boom")) == "无法设置开机自启动：boom"


def test_settings_saved_notice():
    assert settings_saved_notice() == Notice("设置已保存", "新设置已经生效。")


# --- M3 WI-10: model list problem (F11-7) ------------------------------------------

from snapocr.actions.messages import models_problem_text  # noqa: E402


@pytest.mark.parametrize("kind, why", [
    (TranslationErrorKind.UNREACHABLE, "翻译服务没有运行"),
    (TranslationErrorKind.TIMEOUT, "翻译服务没有响应"),
    (TranslationErrorKind.CONNECTION, "连接中断"),
    (TranslationErrorKind.HTTP_STATUS, "服务不支持读取模型列表"),
    (TranslationErrorKind.BAD_RESPONSE, "服务不支持读取模型列表"),
])
def test_models_problem_text(kind, why):
    err = TranslationError(kind, base_url="http://127.0.0.1:11434", model="hy-mt2:7b")
    assert models_problem_text(err) == f"没能读取模型列表（{why}），可以直接输入模型名。"


# --- M3 WI-11: OCR notice without the text (F7-2) -------------------------------------


def test_ocr_ok_notice_without_text_counts_characters():
    n = ocr_ok_notice("使用 Python3 截图，\n  自动复制。", show_text=False)
    assert n == Notice("已复制 OCR 文本", "共 17 个字")  # whitespace not counted


def test_ocr_ok_notice_show_text_default_is_the_preview():
    assert ocr_ok_notice("你好 world") == ocr_ok_notice("你好 world", show_text=True) == Notice("已复制 OCR 文本", "你好 world")


@given(st.text(max_size=300))
def test_ocr_ok_notice_without_text_never_shows_it(text):
    n = ocr_ok_notice(text + "⟦M7⟧", show_text=False)
    assert "⟦M7⟧" not in n.body and "M7" not in n.body
    assert n.body == f"共 {len(''.join((text + '⟦M7⟧').split()))} 个字"
