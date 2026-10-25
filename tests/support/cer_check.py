"""Test-side CER gate (WI-9, PRD F1-7).

Decisions (documented here because tests depend on them):

* Both ``hyp`` and ``ref`` are passed through ``normalize_for_cer`` (all
  whitespace removed) before anything is computed. Indices in the failure
  message refer to the NORMALIZED strings.
* The limit is a closed interval: ``cer <= limit`` passes.
* An empty hyp against a non-empty ref is an ordinary recognition failure:
  ``AssertionError`` with CER 1.0000 (``metrics.cer`` returns 1.0 there).
* An empty ref (after normalization) is a broken fixture, not an OCR result:
  ``ValueError``. Otherwise an empty hyp would pass vacuously (0/0) and a
  non-empty hyp would leak ``metrics.cer``'s own ValueError.
* The failure message shows CER with 4 decimals, the edit distance, the first
  differing index, and ~10 characters of context from both sides. This is
  test output, not a log.
"""

from snapocr.metrics import cer, edit_distance, normalize_for_cer

_CONTEXT = 5


def first_difference(a: str, b: str) -> int:
    """First index where ``a`` and ``b`` differ; ``min(len)`` if one is a prefix.

    Returns -1 when the strings are equal.
    """
    for i, (ca, cb) in enumerate(zip(a, b)):
        if ca != cb:
            return i
    if len(a) == len(b):
        return -1
    return min(len(a), len(b))


def assert_cer_within(hyp: str, ref: str, limit: float, label: str = "") -> float:
    """Assert CER(normalize(hyp), normalize(ref)) <= limit; return the CER."""
    h = normalize_for_cer(hyp)
    r = normalize_for_cer(ref)
    if not r:
        raise ValueError(f"{label or 'cer'}: reference is empty after normalization")
    value = cer(h, r)
    if value <= limit:
        return value
    i = first_difference(h, r)
    lo, hi = max(0, i - _CONTEXT), i + _CONTEXT
    raise AssertionError(
        f"{label or 'cer'}: CER {value:.4f} > limit {limit:.4f} "
        f"(distance {edit_distance(h, r)}/{len(r)}); "
        f"first difference at index {i} (normalized): "
        f"ref[{lo}:{hi}]={r[lo:hi]!r} hyp[{lo}:{hi}]={h[lo:hi]!r}"
    )
