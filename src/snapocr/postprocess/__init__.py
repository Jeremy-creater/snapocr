"""F2 text post-processing (stdlib only; no OCR runtime imports).

Public API: ``postprocess(result, options)`` turns an ``OcrResult`` into text by
running the rules in ``RULE_ORDER``; ``PostprocessOptions`` switches the
optional rules. See ``docs/postprocess.md``.
"""

from snapocr.postprocess.pipeline import RULE_ORDER, PostprocessOptions, postprocess

__all__ = ["RULE_ORDER", "PostprocessOptions", "postprocess"]
