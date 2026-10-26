"""F4 translation client (stdlib only; no OCR runtime imports).

Public API: ``OpenAICompatTranslator(TranslatorConfig()).translate(text)`` returns a
``TranslationResult`` or raises ``TranslationError``. Only ``http://127.0.0.1:<port>``
services are reachable. Business code should depend on the ``Translator`` protocol.
"""

from snapocr.translators.config import TranslatorConfig
from snapocr.translators.direction import detect_target_lang
from snapocr.translators.errors import TranslationError, TranslationErrorKind, TranslatorConfigError
from snapocr.translators.openai_compat import OpenAICompatTranslator
from snapocr.translators.types import TranslationResult, Translator

__all__ = [
    "OpenAICompatTranslator",
    "TranslationError",
    "TranslationErrorKind",
    "TranslationResult",
    "Translator",
    "TranslatorConfig",
    "TranslatorConfigError",
    "detect_target_lang",
]
