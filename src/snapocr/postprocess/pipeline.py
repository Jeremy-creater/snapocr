"""F2-4 / F2-5 rule chain, switches and entry point (plan WI-6, decision D1).

``postprocess`` runs the rules in ``RULE_ORDER``:

1. ``layout`` (F2-0, always on): ``build_lines`` turns blocks into lines. The
   text region ``(min left, max right)`` is computed once from these lines and
   passed to the paragraph rule explicitly (matrix Q1).
2. ``paragraphs`` (F2-3, optional): ``merge_paragraphs(lines, region=R)``.
   The lines are then always rendered with ``lines_to_text``, so paragraph-gap
   empty lines survive even when this rule is off (Q10).
3. ``spacing`` (F2-1, optional): ``add_cjk_latin_spacing``. It runs after
   ``paragraphs`` so that seams between merged lines get spacing too.
4. ``punctuation`` (F2-2, optional): ``to_fullwidth_punctuation``. It runs
   after ``spacing`` because F2-2 skips spaces when judging the context and
   deletes the spaces around a converted mark.
5. ``finalize`` (always on): see ``finalize``.

There is no ``replacements`` rule in M1 (D1; deferred to M2 together with F9).
See ``docs/postprocess.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, fields

from snapocr.engines.types import OcrResult
from snapocr.postprocess.layout import build_lines
from snapocr.postprocess.paragraphs import lines_to_text, merge_paragraphs
from snapocr.postprocess.punctuation import to_fullwidth_punctuation
from snapocr.postprocess.spacing import add_cjk_latin_spacing

RULE_ORDER: tuple[str, ...] = ("layout", "paragraphs", "spacing", "punctuation", "finalize")


@dataclass(frozen=True)
class PostprocessOptions:
    """Switches for the optional rules; every field must be exactly ``bool``."""

    paragraphs: bool = True
    spacing: bool = True
    punctuation: bool = True

    def __post_init__(self) -> None:
        for f in fields(self):
            value = getattr(self, f.name)
            if type(value) is not bool:
                raise ValueError(f"{f.name}: expected bool, got {type(value).__name__}")


def finalize(text: str) -> str:
    """Strip trailing whitespace of every line and drop leading / trailing empty lines.

    Leading whitespace and internal empty lines are kept; lines are joined
    with LF and there is no final newline.
    """
    if not isinstance(text, str):
        raise TypeError(f"expected str, got {type(text).__name__}")
    lines = [line.rstrip() for line in text.split("\n")]
    start, end = 0, len(lines)
    while start < end and not lines[start]:
        start += 1
    while end > start and not lines[end - 1]:
        end -= 1
    return "\n".join(lines[start:end])


def postprocess(result: OcrResult, options: PostprocessOptions | None = None) -> str:
    """Turn ``result`` into text by running the enabled rules in ``RULE_ORDER``."""
    if not isinstance(result, OcrResult):
        raise TypeError(f"expected OcrResult, got {type(result).__name__}")
    if options is None:
        options = PostprocessOptions()
    elif not isinstance(options, PostprocessOptions):
        raise TypeError(f"options: expected PostprocessOptions, got {type(options).__name__}")

    lines = build_lines(result)
    if lines and options.paragraphs:
        region = (min(line.left for line in lines), max(line.right for line in lines))
        lines = merge_paragraphs(lines, region=region)
    text = lines_to_text(lines)
    if options.spacing:
        text = add_cjk_latin_spacing(text)
    if options.punctuation:
        text = to_fullwidth_punctuation(text)
    return finalize(text)
