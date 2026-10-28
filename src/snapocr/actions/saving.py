"""Write the screenshot file (PRD v1.1 F17-1, F17-3, F17-4; M4 plan D26, D29). No Qt.

Runs on the GUI thread when the capture overlay's "save" is chosen: the
save-as dialog starts at ``suggest_path`` (``snapocr_YYYYMMDD_HHMMSS.png``
with ``_2``, ``_3`` ... for the same second, first one free in the save
folder), then ``save_flow`` writes the file the user picked. Saved or not,
the PNG goes to the clipboard.
"""

from __future__ import annotations

import datetime
import itertools
import logging
from collections.abc import Iterator
from pathlib import Path

from snapocr.actions.messages import save_failed_notice
from snapocr.actions.outcomes import ClipboardPng, Outcome

_log = logging.getLogger(__name__)


def save_names(now: datetime.datetime) -> Iterator[str]:
    """F17-3: the candidate file names for ``now``, in order (endless)."""
    stem = f"snapocr_{now:%Y%m%d_%H%M%S}"
    return itertools.chain([f"{stem}.png"], map(f"{stem}_{{}}.png".format, itertools.count(2)))


def suggest_path(folder: Path, now: datetime.datetime) -> Path:
    """F17-2, F17-3: the dialog's preset; creates ``folder``, or leaves a folder it cannot create to the dialog."""
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as err:
        _log.warning("save folder not created: %s", type(err).__name__)
    return next(path for path in map(folder.joinpath, save_names(now)) if not path.exists())


def save_flow(png: bytes, path: Path) -> Outcome:
    """F17-1, F17-4: write ``png`` to ``path`` (the dialog confirmed any replace); the PNG goes to the clipboard either way."""
    try:
        path.write_bytes(png)
    except OSError as err:
        _log.warning("screenshot not saved: %s", type(err).__name__)
        return Outcome(ClipboardPng(png), save_failed_notice(path, err.strerror or type(err).__name__), None)
    return Outcome(ClipboardPng(png), None, None)
