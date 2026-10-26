"""F2 text post-processing (stdlib only; no OCR runtime imports).

Public API: ``postprocess(result, options, replacements)`` turns an
``OcrResult`` into text by running the rules in ``RULE_ORDER``;
``PostprocessOptions`` switches the optional rules and ``Replacements`` is the
F2-6 table (empty by default). See ``docs/postprocess.md``.
"""

from snapocr.postprocess.pipeline import RULE_ORDER, PostprocessOptions, postprocess
from snapocr.postprocess.replacements import ReplacementError, Replacements

__all__ = ["RULE_ORDER", "PostprocessOptions", "ReplacementError", "Replacements", "postprocess"]
