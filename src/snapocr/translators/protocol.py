"""OpenAI-compatible chat protocol as pure functions (F4-2, F4-3, F4-5).

No I/O here: requests are built as bytes and responses are parsed from
``(status, body)``; ``http_transport`` moves the bytes.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from snapocr.translators.config import (
    SOURCE_PLACEHOLDER,
    TARGET_PLACEHOLDER,
    TranslatorConfig,
)
from snapocr.translators.errors import ErrorContext, TranslationError, TranslationErrorKind
from snapocr.translators.types import TargetLang

CHAT_PATH = "/v1/chat/completions"
_LANGUAGE_NAMES = {"en": "英语", "zh": "中文"}
_HEADERS: Mapping[str, str] = MappingProxyType(
    {"Content-Type": "application/json", "Accept": "application/json"}
)


@dataclass(frozen=True)
class ChatRequest:
    path: str
    headers: Mapping[str, str]
    body: bytes


def _language_name(target_lang: object) -> str:
    if not isinstance(target_lang, str) or target_lang not in _LANGUAGE_NAMES:
        raise ValueError("target_lang: expected 'zh' or 'en'")
    return _LANGUAGE_NAMES[target_lang]


def render_prompt(template: str, target_lang: TargetLang, source_text: str) -> str:
    """Literal substitution, source text last, so placeholders inside it stay untouched (D8)."""
    name = _language_name(target_lang)
    return template.replace(TARGET_PLACEHOLDER, name).replace(SOURCE_PLACEHOLDER, source_text, 1)


def build_chat_request(
    config: TranslatorConfig, target_lang: TargetLang, source_text: str
) -> ChatRequest:
    prompt = render_prompt(config.prompt_template, target_lang, source_text)
    body = {
        "model": config.model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        **config.sampling,
    }
    # Q5: ASCII-only JSON round-trips every str, lone surrogates included.
    encoded = json.dumps(body, ensure_ascii=True, allow_nan=False).encode("ascii")
    return ChatRequest(CHAT_PATH, _HEADERS, encoded)



# --- response side ------------------------------------------------------------

_THINK_OPEN = "<think>"
_THINK_CLOSE = "</think>"
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)


def clean_output(s: str) -> str:
    """Remove reasoning blocks (Q11: exact lower-case tags only), then strip.

    1. drop every ``<think>...</think>`` block (non-greedy, across lines);
    2. an unpaired ``</think>`` left over drops everything up to its last one;
    3. an unpaired ``<think>`` left over drops everything from it to the end.
    """
    s = _THINK_BLOCK.sub("", s)
    close = s.rfind(_THINK_CLOSE)
    if close != -1:
        s = s[close + len(_THINK_CLOSE):]
    opening = s.find(_THINK_OPEN)
    if opening != -1:
        s = s[:opening]
    return s.strip()


_NOT_JSON = object()


def _load_json(body: bytes) -> object:
    """Decoded JSON value, ``_NOT_JSON`` or ``None`` for non-UTF-8.

    Exceptions are swallowed here so the caller raises outside any ``except``
    block: ``JSONDecodeError.doc`` / ``UnicodeDecodeError.object`` hold the
    whole body and must not hang on ``__context__`` (Q12).
    """
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        return None
    try:
        return json.loads(text)
    except (ValueError, RecursionError):
        return _NOT_JSON


def _fail(kind: TranslationErrorKind, ctx: ErrorContext, detail: str, status: int | None = None):
    return TranslationError(
        kind, base_url=ctx.base_url, model=ctx.model, detail=detail, status=status
    )


def _mentions_model(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    error = value.get("error")
    if isinstance(error, dict):
        error = error.get("message")
    return isinstance(error, str) and "model" in error.lower()


def _content_or_problem(value: object) -> tuple[str | None, str, object]:
    """(content, problem, finish_reason); content is None when the shape is wrong."""
    if not isinstance(value, dict):
        return None, "not a JSON object", None
    choices = value.get("choices")
    if not isinstance(choices, list) or not choices:
        return None, "no choices", None
    choice = choices[0]
    if not isinstance(choice, dict):
        return None, "choice is not an object", None
    message = choice.get("message")
    if not isinstance(message, dict):
        return None, "message is not an object", None
    content = message.get("content")
    if not isinstance(content, str):
        return None, "content is not a string", None
    return content, "", choice.get("finish_reason")


def parse_chat_response(status: int, body: bytes, *, ctx: ErrorContext) -> str:
    """Translated text from a ``(status, body)`` pair, or ``TranslationError``.

    Nothing from the body ever reaches the error (privacy); details are fixed phrases.
    """
    value = _load_json(body)
    if status != 200:
        kind = TranslationErrorKind.HTTP_STATUS
        if status == 404 and _mentions_model(value):
            kind = TranslationErrorKind.MODEL_NOT_FOUND
        raise _fail(kind, ctx, f"HTTP {status}", status)
    if value is None:
        raise _fail(TranslationErrorKind.BAD_RESPONSE, ctx, "not UTF-8")
    if value is _NOT_JSON:
        raise _fail(TranslationErrorKind.BAD_RESPONSE, ctx, "not JSON")
    content, problem, finish_reason = _content_or_problem(value)
    if content is None:
        raise _fail(TranslationErrorKind.BAD_RESPONSE, ctx, problem)
    if finish_reason == "length":
        raise _fail(TranslationErrorKind.TRUNCATED, ctx, "finish_reason=length")
    text = clean_output(content)
    if not text:
        raise _fail(TranslationErrorKind.EMPTY_OUTPUT, ctx, "no text after removing <think> blocks")
    return text
