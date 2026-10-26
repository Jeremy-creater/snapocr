"""Translator configuration and loopback-only base_url validation (F4-6, D2).

Only ``http://127.0.0.1:<port>`` is accepted: there is no option that lets a
request leave the machine (CLAUDE.md). Ollama cloud model names are rejected
too, since Ollama would forward the text (PRD F4-6, review C1). Stdlib only.
"""

from __future__ import annotations

import math
import numbers
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from snapocr.translators.errors import TranslatorConfigError

LOOPBACK_HOST = "127.0.0.1"
DEFAULT_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "hy-mt2:7b"
DEFAULT_PROMPT_TEMPLATE = "把下面的文本翻译成{target_language}，不要额外解释。\n\n{source_text}"
DEFAULT_SAMPLING: Mapping[str, object] = MappingProxyType({"temperature": 0.7, "top_p": 0.8})

SOURCE_PLACEHOLDER = "{source_text}"
TARGET_PLACEHOLDER = "{target_language}"

# Q4: one strict regex instead of urlsplit (port parsing, case and a trailing
# "\n" matched by "$" are all bypass surfaces). [0-9] is ASCII-only.
_BASE_URL_RE = re.compile(r"http://127\.0\.0\.1:([1-9][0-9]{0,4})/?")

_TARGET_LANGS = ("auto", "zh", "en")

# Q16: OpenAI-compatible sampling fields only; real-valued ones with their range.
_REAL_SAMPLING = {
    "temperature": (0.0, 2.0),
    "top_p": (0.0, 1.0),
    "presence_penalty": (-2.0, 2.0),
    "frequency_penalty": (-2.0, 2.0),
}
_INT_SAMPLING = ("max_tokens", "seed")
SAMPLING_KEYS = frozenset(_REAL_SAMPLING) | frozenset(_INT_SAMPLING) | {"stop"}


def _is_real(value: object) -> bool:
    return isinstance(value, numbers.Real) and not isinstance(value, bool)


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


@dataclass(frozen=True)
class Endpoint:
    """A validated loopback endpoint. Cannot be built or modified to point elsewhere (Q3)."""

    host: str
    port: int
    url: str

    def __post_init__(self) -> None:
        if (
            self.host != LOOPBACK_HOST
            or not _is_int(self.port)
            or not 1 <= self.port <= 65535
            or self.url != f"http://{LOOPBACK_HOST}:{self.port}"
        ):
            raise TranslatorConfigError(
                "endpoint must be http://127.0.0.1:<port>", key="base_url"
            )


def parse_base_url(s: object) -> Endpoint:
    if not isinstance(s, str):
        raise TranslatorConfigError(
            f"expected str, got {type(s).__name__}", key="base_url"
        )
    m = _BASE_URL_RE.fullmatch(s)
    if m is None or int(m.group(1)) > 65535:
        hints = []
        if "localhost" in s.lower():
            hints.append("改成 127.0.0.1")
        if s.rstrip("/").endswith("/v1"):
            hints.append("base_url 不要带 /v1（接口路径是 {base_url}/v1/chat/completions）")
        message = "only http://127.0.0.1:<port> (port 1-65535, no path) is allowed"
        if hints:
            message = f"{message}; {'; '.join(hints)}"
        raise TranslatorConfigError(message, key="base_url")
    port = int(m.group(1))
    return Endpoint(LOOPBACK_HOST, port, f"http://{LOOPBACK_HOST}:{port}")


def _check_sampling(sampling: object) -> Mapping[str, object]:
    if not isinstance(sampling, Mapping):
        raise TranslatorConfigError(
            f"expected a mapping, got {type(sampling).__name__}", key="sampling"
        )
    checked: dict[str, object] = {}
    for name, value in sampling.items():
        if name not in SAMPLING_KEYS:
            raise TranslatorConfigError(
                f"{name!r} is not an allowed field ({', '.join(sorted(SAMPLING_KEYS))})",
                key="sampling",
            )
        if name in _REAL_SAMPLING:
            lo, hi = _REAL_SAMPLING[name]
            if not _is_real(value) or not math.isfinite(value) or not lo <= value <= hi:
                raise TranslatorConfigError(
                    f"{name} must be a real number in [{lo}, {hi}]", key="sampling"
                )
        elif name in _INT_SAMPLING:
            if not _is_int(value) or (name == "max_tokens" and value < 1):
                raise TranslatorConfigError(
                    f"{name} must be an int" + (" >= 1" if name == "max_tokens" else ""),
                    key="sampling",
                )
        else:  # stop
            if isinstance(value, (list, tuple)) and all(isinstance(v, str) for v in value):
                value = tuple(value)
            elif not isinstance(value, str):
                raise TranslatorConfigError(
                    "stop must be a str or a list of str", key="sampling"
                )
        checked[name] = value
    return MappingProxyType(checked)


@dataclass(frozen=True)
class TranslatorConfig:
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    timeout_s: float = 60.0
    target_lang: str = "auto"
    direction_threshold: float = 0.3
    prompt_template: str = DEFAULT_PROMPT_TEMPLATE
    sampling: Mapping[str, object] = DEFAULT_SAMPLING
    max_input_chars: int = 4000
    endpoint: Endpoint = field(init=False, repr=False)

    def __post_init__(self) -> None:
        endpoint = parse_base_url(self.base_url)

        m = self.model
        if (
            not isinstance(m, str)
            or not m
            or m != m.strip()
            or any(unicodedata.category(c) == "Cc" for c in m)
        ):
            raise TranslatorConfigError(
                "must be a non-empty str without surrounding whitespace or control characters",
                key="model",
            )
        tag = m.rpartition(":")[2].lower() if ":" in m else ""
        if tag == "cloud" or tag.endswith("-cloud"):
            # Review C1: Ollama forwards cloud models' input to ollama.com.
            raise TranslatorConfigError(
                "Ollama cloud models (tag 'cloud' or '*-cloud') send text off this machine",
                key="model",
            )

        t = self.timeout_s
        if not _is_real(t) or not math.isfinite(t) or not 0 < t <= 600:
            raise TranslatorConfigError("must be a finite number with 0 < t <= 600", key="timeout_s")

        if not isinstance(self.target_lang, str) or self.target_lang not in _TARGET_LANGS:
            raise TranslatorConfigError("must be 'auto', 'zh' or 'en'", key="target_lang")

        th = self.direction_threshold
        if not _is_real(th) or not math.isfinite(th) or not 0 < th <= 1:
            raise TranslatorConfigError(
                "must be a finite number with 0 < t <= 1", key="direction_threshold"
            )

        tpl = self.prompt_template
        if (
            not isinstance(tpl, str)
            or tpl.count(SOURCE_PLACEHOLDER) != 1
            or tpl.count(TARGET_PLACEHOLDER) > 1
        ):
            raise TranslatorConfigError(
                "must contain {source_text} exactly once and {target_language} at most once",
                key="prompt_template",
            )

        sampling = _check_sampling(self.sampling)

        n = self.max_input_chars
        if not _is_int(n) or n < 1:
            raise TranslatorConfigError("must be an int >= 1", key="max_input_chars")

        object.__setattr__(self, "timeout_s", float(t))
        object.__setattr__(self, "sampling", sampling)
        object.__setattr__(self, "endpoint", endpoint)
