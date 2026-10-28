"""User-facing texts for tray notices, the popup and the settings window (PRD F5-3, F7-2 to F7-4, F8-4, F9-3, F11).

None of these builders takes OCR or translated text except ``ocr_ok_notice``,
which shows the 30-character preview that F7-2 asks for.
"""

from __future__ import annotations

import ntpath
import os
from pathlib import Path
from collections.abc import Mapping, Sequence
from types import MappingProxyType

from snapocr.actions.outcomes import NOTICE_BODY_MAX, Notice
from snapocr.commands import Command
from snapocr.config.schema import ConfigIssue
from snapocr.config.settings import BadModel, BadSaveDir, DuplicateHotkey, Problem
from snapocr.engines.errors import EngineLoadError, OcrError
from snapocr.hotkeys import ERROR_HOTKEY_ALREADY_REGISTERED, HotkeyFailure, format_hotkey
from snapocr.translators.errors import TranslationError, TranslationErrorKind

COMMAND_LABELS: Mapping[Command, str] = MappingProxyType(
    {
        Command.CAPTURE: "截图",
        Command.OCR: "OCR",
        Command.TRANSLATE: "翻译",
        Command.LAST_RESULT: "上次结果",
        Command.SETTINGS: "设置…",
        Command.OPEN_CONFIG: "打开配置文件",
        Command.QUIT: "退出",
        Command.CODE_OCR: "代码 OCR",
        Command.TABLE_OCR: "表格 OCR",
    }
)

_UNCHANGED = "剪贴板没有改动。"

NOTHING_TO_TRANSLATE = "没有可翻译的文字"


def preview(text: str, n: int = 30) -> str:
    """Whitespace runs (newlines too) become one space; at most n code points, then "…"."""
    flat = " ".join(text.split())
    return flat if len(flat) <= n else flat[:n] + "…"


def ocr_ok_notice(text: str, show_text: bool = True) -> Notice:
    """F7-2: the preview, or only the count of non-whitespace characters when ``show_text`` is off."""
    if not show_text:
        return Notice("已复制 OCR 文本", f"共 {len(''.join(text.split()))} 个字")
    return Notice("已复制 OCR 文本", preview(text))


def code_ok_notice(text: str, show_text: bool = True) -> Notice:
    """F13-1: like ``ocr_ok_notice``, titled for code."""
    return Notice("已复制代码", ocr_ok_notice(text, show_text).body)


def table_ok_notice(rows: int, cols: int) -> Notice:
    """F16-1: the table's size, never its text."""
    return Notice("已复制表格", f"{rows} 行 × {cols} 列")


def save_failed_notice(path: Path, reason: str) -> Notice:
    """F17-4: why, and the file it was meant to be; the image is on the clipboard anyway."""
    return Notice("保存失败", f"{reason}\n{path}", warning=True)


def ocr_empty_notice() -> Notice:
    return Notice("未识别到文字", _UNCHANGED)


# A model file name longer than this is cut (ending with "…").
_MAX_FILE_NAME = 60


def engine_failed_notice(err: EngineLoadError, log_file: Path) -> Notice:
    """A short reason, then the log file (F7-4, M3 WI-9).

    The fix command, every model path and the cause are in the log (written by
    ``actions.flows``) and in the "last result" record, not here: the real fix
    command alone is about 200 code points. The log path always shows whole;
    the reason is shortened to make room for it.
    """
    if err.model_paths:
        name = ntpath.basename(os.fspath(err.model_paths[0]))
        if len(name) > _MAX_FILE_NAME:
            name = name[: _MAX_FILE_NAME - 1] + "…"
        more = f" 等 {len(err.model_paths)} 个" if len(err.model_paths) > 1 else ""
        reason = f"模型文件缺失或损坏：{name}{more}"
    else:
        reason = "OCR 引擎没能初始化"
    where = f"完整原因和修复命令见日志：{log_file}"
    room = NOTICE_BODY_MAX - len(where) - 1
    if len(reason) > room:
        reason = reason[: max(room - 1, 0)] + "…"
    return Notice("OCR 引擎加载失败", f"{reason}\n{where}", warning=True)


def ocr_failed_notice(err: OcrError) -> Notice:
    return Notice("OCR 失败", f"{err}\n{_UNCHANGED}", warning=True)


def translation_error_text(err: TranslationError) -> str:
    return f"翻译失败：{err}"


def hotkey_failure_line(f: HotkeyFailure) -> str:
    if f.error_code == ERROR_HOTKEY_ALREADY_REGISTERED:
        why = "已被其他软件占用"
    else:
        why = f"注册失败，错误码 {f.error_code}"
    return f"{f.hotkey_text}（{COMMAND_LABELS[f.command]}）：{why}"


def hotkey_failed_notice(failures: Sequence[HotkeyFailure]) -> Notice:
    if not failures:
        raise ValueError("no hotkey failures to report")
    lines = [hotkey_failure_line(f) for f in failures]
    lines.append("其余热键照常工作。可以在托盘菜单的“设置…”里换一个组合（或改 config.local.toml 的 [hotkeys]）。")
    return Notice(f"有 {len(failures)} 个热键注册失败", "\n".join(lines), warning=True)


def config_issues_notice(issues: Sequence[ConfigIssue]) -> Notice:
    if not issues:
        raise ValueError("no config issues to report")
    return Notice(f"配置文件有 {len(issues)} 个问题", "\n".join(str(i) for i in issues), warning=True)



def capture_failed_notice(detail: str) -> Notice:
    return Notice("截图失败", f"{detail}\n{_UNCHANGED}", warning=True)


def job_crashed_text(exc_type_name: str) -> str:
    return f"内部错误（{exc_type_name}），详情见日志"


def job_crashed_notice(exc_type_name: str) -> Notice:
    return Notice("操作失败", f"{job_crashed_text(exc_type_name)}。{_UNCHANGED}", warning=True)


def config_opened_notice() -> Notice:
    return Notice("已打开配置文件", "修改后重启 snapocr 生效。")


def open_config_failed_notice(path: os.PathLike[str] | str, detail: str) -> Notice:
    return Notice("无法打开配置文件", f"{os.fspath(path)}\n{detail}", warning=True)


def settings_problem_text(p: Problem) -> str:
    if isinstance(p, DuplicateHotkey):
        first, second = COMMAND_LABELS[p.first], COMMAND_LABELS[p.second]
        return f"「{first}」和「{second}」用了同一个热键 {format_hotkey(p.hotkey)}。"
    if isinstance(p, BadModel):
        return f"模型名不能用：{p.reason}"
    if isinstance(p, BadSaveDir):
        return "「截图保存到」必须是完整的文件夹路径，例如 D:/截图。"
    return "目标语言只能是自动、中文或英文。"


def autostart_failed_text(err: OSError) -> str:
    return f"无法设置开机自启动：{err.strerror or err}"


def settings_saved_notice() -> Notice:
    return Notice("设置已保存", "新设置已经生效。")


MODELS_LOADING = "正在读取模型列表…"

_MODELS_PROBLEM = {
    TranslationErrorKind.UNREACHABLE: "翻译服务没有运行",
    TranslationErrorKind.TIMEOUT: "翻译服务没有响应",
    TranslationErrorKind.CONNECTION: "连接中断",
}


def models_problem_text(err: TranslationError) -> str:
    """Why the settings window has no model list (F11-7); never blocks saving."""
    why = _MODELS_PROBLEM.get(err.kind, "服务不支持读取模型列表")
    return f"没能读取模型列表（{why}），可以直接输入模型名。"


def debug_on_notice(directory: Path) -> Notice:
    """F12-2: shown at start while debug mode is on."""
    return Notice("debug 模式已开启", f"截图和识别全文会保存到：{directory}")
