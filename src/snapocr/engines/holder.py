"""Lazy, reusable holder for an OCR engine (F1-5).

The holder is owned by the application wiring code; there is no module-level
singleton. Loading happens on the first ``get()`` and the engine is reused
afterwards. Failures are never cached, so a later ``get()`` retries.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from snapocr.engines.errors import EngineLoadError
from snapocr.engines.types import OcrEngine

_WRAP_HINT = "check the OCR model files and engine settings, then try again"


class EngineHolder:
    def __init__(self, factory: Callable[[], OcrEngine]) -> None:
        self._factory = factory
        self._engine: OcrEngine | None = None
        self._lock = threading.Lock()

    def get(self) -> OcrEngine:
        """Return the loaded engine, loading it on first use.

        Raises ``EngineLoadError`` for any ``Exception`` from the factory; an
        ``EngineLoadError`` raised by the factory propagates unchanged.
        ``BaseException`` subclasses such as ``KeyboardInterrupt`` are not caught.
        """
        with self._lock:
            if self._engine is None:
                try:
                    self._engine = self._factory()
                except EngineLoadError:
                    raise
                except Exception as exc:
                    raise EngineLoadError(
                        model_paths=(),
                        hint=_WRAP_HINT,
                        detail=f"{type(exc).__name__}: {exc}",
                    ) from exc
            return self._engine
