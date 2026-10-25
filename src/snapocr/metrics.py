"""Character error rate (CER) metrics for OCR evaluation.

Pure stdlib. Strings are compared by Unicode code point; no Unicode
normalization (NFKC, width folding) is applied, because punctuation and
width differences are errors the evaluation must see.
"""


def edit_distance(a: str, b: str) -> int:
    """Levenshtein distance: insert, delete, substitute each cost 1; no transposition."""
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(
                min(
                    previous[j] + 1,  # delete from a
                    current[j - 1] + 1,  # insert into a
                    previous[j - 1] + (ca != cb),  # substitute or match
                )
            )
        previous = current
    return previous[-1]


def cer(hyp: str, ref: str) -> float:
    """edit_distance(hyp, ref) / len(ref); not clamped to 1.

    Both empty -> 0.0. Empty ref with non-empty hyp is undefined -> ValueError.
    """
    if not ref:
        if hyp:
            raise ValueError("ref is empty: CER is undefined for a non-empty hyp")
        return 0.0
    return edit_distance(hyp, ref) / len(ref)


def normalize_for_cer(s: str) -> str:
    """Remove every whitespace character (str.isspace); nothing else changes."""
    return "".join(c for c in s if not c.isspace())
