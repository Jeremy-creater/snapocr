"""Translator for OpenAI-compatible local services (Ollama by default), F4-1..F4-6.

Order of checks per call (matrix Q14): type -> blank -> length -> direction.
Blank and letter-less input never reaches the service. The source text and the
translation never appear in logs or exceptions; only kind, status, elapsed time
and length are logged, at DEBUG.
"""

from __future__ import annotations

import logging
import time

from snapocr.translators.config import TranslatorConfig
from snapocr.translators.direction import resolve_target
from snapocr.translators.errors import ErrorContext, TranslationError, TranslationErrorKind
from snapocr.translators.http_transport import get_json, post_json
from snapocr.translators.protocol import MODELS_PATH, build_chat_request, parse_chat_response, parse_models_response
from snapocr.translators.types import TranslationResult

log = logging.getLogger(__name__)


class OpenAICompatTranslator:
    def __init__(self, config: TranslatorConfig) -> None:
        if not isinstance(config, TranslatorConfig):
            raise TypeError(f"config: expected TranslatorConfig, got {type(config).__name__}")
        self._config = config
        self._ctx = ErrorContext(config.endpoint.url, config.model)

    def translate(self, text: str) -> TranslationResult:
        if not isinstance(text, str):
            raise TypeError(f"text: expected str, got {type(text).__name__}")
        if not text.strip():
            return TranslationResult("", None, True)
        config = self._config
        n = len(text)
        if n > config.max_input_chars:
            raise TranslationError(
                TranslationErrorKind.INPUT_TOO_LONG,
                base_url=self._ctx.base_url,
                model=self._ctx.model,
                detail=f"{n} > {config.max_input_chars} code points",
            )
        target = resolve_target(text, config)
        if target is None:  # no Han characters and no ASCII letters (D1)
            return TranslationResult(text, None, True)

        request = build_chat_request(config, target, text)
        kind, status = "OK", None
        start = time.monotonic()
        try:
            status, body = post_json(
                config.endpoint, request, config.timeout_s, ctx=self._ctx
            )
            translated = parse_chat_response(status, body, ctx=self._ctx)
        except TranslationError as err:
            kind = err.kind.name
            raise
        finally:
            log.debug(
                "translate kind=%s status=%s elapsed_ms=%d chars=%d",
                kind,
                status,
                (time.monotonic() - start) * 1000,
                n,
            )
        return TranslationResult(translated, target, False)


# Fixed, not ``config.timeout_s`` (60 s for cold starts). Windows reports a refused
# loopback connection only after about 2 s; 3 s keeps that an UNREACHABLE (M3 plan D12).
MODEL_LIST_TIMEOUT_S = 3.0


def list_models(config: TranslatorConfig) -> tuple[str, ...]:
    """The models the service at ``config.base_url`` offers (``GET /v1/models``, F11-7)."""
    ctx = ErrorContext(config.endpoint.url, config.model)
    status, body = get_json(config.endpoint, MODELS_PATH, MODEL_LIST_TIMEOUT_S, ctx=ctx)
    return parse_models_response(status, body, ctx=ctx)
