"""User-facing texts for tray notices and the popup (PRD F5-3, F7-2 to F7-4, F8-4, F9-3).

None of these builders takes OCR or translated text except ``ocr_ok_notice``,
which shows the 30-character preview that F7-2 asks for.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from types import MappingProxyType

from snapocr.actions.outcomes import NOTICE_BODY_MAX, Notice
from snapocr.commands import Command
from snapocr.config.schema import ConfigIssue
from snapocr.engines.errors import EngineLoadError, OcrError
from snapocr.hotkeys import ERROR_HOTKEY_ALREADY_REGISTERED, HotkeyFailure
from snapocr.translators.errors import TranslationError

COMMAND_LABELS: Mapping[Command, str] = MappingProxyType(
    {
        Command.CAPTURE: "截图",
        Command.OCR: "OCR",
        Command.TRANSLATE: "翻译",
        Command.LAST_RESULT: "上次结果",
        Command.OPEN_CONFIG: "打开配置文件",
        Command.QUIT: "退出",
    }
)

_UNCHANGED = "剪贴板没有改动。"

NOTHING_TO_TRANSLATE = "没有可翻译的文字"


def preview(text: str, n: int = 30) -> str:
    """Whitespace runs (newlines too) become one space; at most n code points, then "…"."""
    flat = " ".join(text.split())
    return flat if len(flat) <= n else flat[:n] + "…"


def ocr_ok_notice(text: str) -> Notice:
    return Notice("已复制 OCR 文本", preview(text))


def ocr_empty_notice() -> Notice:
    return Notice("未识别到文字", _UNCHANGED)


# A fix line is never cut shorter than this, even next to a very long first path.
_MIN_FIX = 40


def engine_failed_notice(err: EngineLoadError) -> Notice:
    """Fix, then model files, then the cause; the full ``str(err)`` goes to the log.

    The fix and the first model path always fit: when they do not fit together,
    the fix is shortened (ending with "…") so the first path stays whole.
    Further paths and the cause fill what is left.
    """
    fix = f"修复：{err.hint}"
    parts = []
    if err.model_paths:
        paths = [os.fspath(p) for p in err.model_paths]
        # One more for the "…" that Notice adds if later paths or the cause are cut.
        room = max(_MIN_FIX, NOTICE_BODY_MAX - len(f"\n模型文件：{paths[0]}") - 1)
        if len(fix) > room:
            fix = fix[: room - 1] + "…"
        parts.append("模型文件：" + "；".join(paths))
    if err.detail:
        parts.append(f"原因：{err.detail}")
    return Notice("OCR 引擎加载失败", "\n".join([fix, *parts]))


def ocr_failed_notice(err: OcrError) -> Notice:
    return Notice("OCR 失败", f"{err}\n{_UNCHANGED}")


def translation_error_text(err: TranslationError) -> str:
    return f"翻译失败：{err}"


def _hotkey_line(f: HotkeyFailure) -> str:
    if f.error_code == ERROR_HOTKEY_ALREADY_REGISTERED:
        why = "已被其他软件占用"
    else:
        why = f"注册失败，错误码 {f.error_code}"
    return f"{f.hotkey_text}（{COMMAND_LABELS[f.command]}）：{why}"


def hotkey_failed_notice(failures: Sequence[HotkeyFailure]) -> Notice:
    if not failures:
        raise ValueError("no hotkey failures to report")
    lines = [_hotkey_line(f) for f in failures]
    lines.append("其余热键照常工作。可以在 config.local.toml 的 [hotkeys] 里换一个组合。")
    return Notice(f"有 {len(failures)} 个热键注册失败", "\n".join(lines))


def config_issues_notice(issues: Sequence[ConfigIssue]) -> Notice:
    if not issues:
        raise ValueError("no config issues to report")
    return Notice(f"配置文件有 {len(issues)} 个问题", "\n".join(str(i) for i in issues))
