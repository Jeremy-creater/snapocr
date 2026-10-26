"""OpenAI-compatible chat protocol as pure functions (F4-2, F4-3, F4-5).

No I/O here: requests are built as bytes and responses are parsed from
``(status, body)``; ``http_transport`` moves the bytes.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from snapocr.translators.config import (
    SOURCE_PLACEHOLDER,
    TARGET_PLACEHOLDER,
    TranslatorConfig,
)
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
