"""Translation error hierarchy (F4-5). Stdlib only.

``TranslationError`` deliberately has no parameter for the source text or the
response body: neither may end up in an exception message (privacy, CLAUDE.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TranslationErrorKind(Enum):
    UNREACHABLE = "unreachable"
    TIMEOUT = "timeout"
    CONNECTION = "connection"
    MODEL_NOT_FOUND = "model_not_found"
    HTTP_STATUS = "http_status"
    BAD_RESPONSE = "bad_response"
    EMPTY_OUTPUT = "empty_output"
    TRUNCATED = "truncated"
    INPUT_TOO_LONG = "input_too_long"


_HINTS = {
    TranslationErrorKind.UNREACHABLE: "启动 Ollama（`ollama serve`）或检查 base_url",
    TranslationErrorKind.TIMEOUT: "冷启动约 15 s，可调大 timeout_s",
    TranslationErrorKind.CONNECTION: "连接中断，重启 Ollama 后重试",
    TranslationErrorKind.MODEL_NOT_FOUND: (
        "`ollama list` 确认模型名；默认模型用 "
        "`ollama create hy-mt2:7b -f docs/hy-mt2-7b.Modelfile` 导入"
    ),
    TranslationErrorKind.HTTP_STATUS: "查看 Ollama 日志",
    TranslationErrorKind.BAD_RESPONSE: (
        "确认 base_url 指向 OpenAI 兼容服务（/v1/chat/completions）"
    ),
    TranslationErrorKind.EMPTY_OUTPUT: "模型没有输出译文，检查 prompt_template 或换模型",
    TranslationErrorKind.TRUNCATED: "输出被截断，调大或去掉 sampling 里的 max_tokens",
    TranslationErrorKind.INPUT_TOO_LONG: "缩短选区，或调大 max_input_chars",
}


@dataclass(frozen=True)
class ErrorContext:
    """What an error message may name: the service and the model, nothing else."""

    base_url: str
    model: str


class TranslationError(Exception):
    def __init__(
        self,
        kind: TranslationErrorKind,
        *,
        base_url: str,
        model: str,
        detail: str = "",
        status: int | None = None,
    ) -> None:
        if not isinstance(kind, TranslationErrorKind):
            raise TypeError(f"kind: expected TranslationErrorKind, got {type(kind).__name__}")
        self.kind = kind
        self.base_url = base_url
        self.model = model
        self.detail = detail
        self.status = status
        head = f"translation failed [{kind.name}]"
        if detail:
            head = f"{head}: {detail}"
        super().__init__(
            f"{head} (base_url={base_url}, model={model}); fix: {_HINTS[kind]}"
        )


class TranslatorConfigError(ValueError):
    """Invalid translator configuration; ``key`` names the offending field."""

    def __init__(self, message: str, *, key: str) -> None:
        self.key = key
        super().__init__(f"{key}: {message}")
