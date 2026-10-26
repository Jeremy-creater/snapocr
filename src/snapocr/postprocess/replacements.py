"""F2-6 custom replacement table (PRD F2-6 v0.4, M2 plan D10). Stdlib only.

``apply`` scans left to right and replaces each key it finds with its value,
then continues after the inserted value; inserted values are never rescanned.
No key is a substring of another, so at most one key matches at a position.

``from_mapping`` enforces the PRD constraints, which make ``apply`` leave no
key behind and so make it idempotent:

- keys and values are non-empty;
- no key is a substring of another key;
- for every key k and value v: k is not in v, v is not in k, no non-empty
  proper suffix of v starts k and no non-empty proper prefix of v ends k.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import ClassVar


class ReplacementError(ValueError):
    """``key`` names the offending entry (``None`` when the table is not a mapping)."""

    def __init__(self, key: object, reason: str) -> None:
        super().__init__(f"{key!r}: {reason}")
        self.key = key
        self.reason = reason


def _check(mapping: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(mapping, Mapping):
        raise ReplacementError(None, f"expected a table of strings, got {type(mapping).__name__}")
    for k, v in mapping.items():
        if not isinstance(k, str):
            raise ReplacementError(k, f"key must be a string, got {type(k).__name__}")
        if not isinstance(v, str):
            raise ReplacementError(k, f"value must be a string, got {type(v).__name__}")
    pairs = tuple(sorted(mapping.items()))
    for k, v in pairs:
        if not k:
            raise ReplacementError(k, "key is empty")
        if not v:
            raise ReplacementError(k, "value is empty (deleting text can join new matches)")
    keys = [k for k, _ in pairs]
    for k in keys:
        for other in keys:
            if k != other and k in other:
                raise ReplacementError(k, f"key is part of another key {other!r}")
    for owner, v in pairs:
        for k in keys:
            if k in v:
                raise ReplacementError(owner, f"value {v!r} contains key {k!r}")
            if v in k:
                raise ReplacementError(owner, f"value {v!r} is part of key {k!r}")
            for i in range(1, len(v)):
                if k.startswith(v[i:]):
                    raise ReplacementError(owner, f"end of value {v!r} can start key {k!r}")
                if k.endswith(v[:i]):
                    raise ReplacementError(owner, f"start of value {v!r} can end key {k!r}")
    return pairs


@dataclass(frozen=True)
class Replacements:
    """A validated table; build it with ``from_mapping``. ``EMPTY`` replaces nothing."""

    pairs: tuple[tuple[str, str], ...] = ()
    _pattern: re.Pattern[str] | None = field(default=None, init=False, repr=False, compare=False)

    EMPTY: ClassVar[Replacements]

    def __post_init__(self) -> None:
        pairs = _check(dict(self.pairs))
        object.__setattr__(self, "pairs", pairs)
        if pairs:
            pattern = re.compile("|".join(re.escape(k) for k, _ in pairs))
            object.__setattr__(self, "_pattern", pattern)

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, str]) -> Replacements:
        return cls(_check(mapping))

    def apply(self, text: str) -> str:
        if not isinstance(text, str):
            raise TypeError(f"expected str, got {type(text).__name__}")
        if self._pattern is None:
            return text
        table = dict(self.pairs)
        return self._pattern.sub(lambda m: table[m.group(0)], text)


Replacements.EMPTY = Replacements()
