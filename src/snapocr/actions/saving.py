"""Save the screenshot into the save folder (PRD F17-1, F17-3, F17-4; M4 plan D24, D26). No Qt.

Runs on the GUI thread when the capture overlay's "save" is chosen: one
small PNG write. Names are ``snapocr_YYYYMMDD_HHMMSS.png`` with ``_2``,
``_3`` ... for the same second; each candidate is opened with exclusive
create, so an existing file is never overwritten. Saved or not, the PNG goes
to the clipboard.
"""

from __future__ import annotations

import datetime
import itertools
import logging
from collections.abc import Iterator
from pathlib import Path

from snapocr.actions.messages import save_failed_notice, save_ok_notice
from snapocr.actions.outcomes import ClipboardPng, Outcome

_log = logging.getLogger(__name__)


def save_names(now: datetime.datetime) -> Iterator[str]:
    """F17-3: the candidate file names for ``now``, in order (endless)."""
    stem = f"snapocr_{now:%Y%m%d_%H%M%S}"
    return itertools.chain([f"{stem}.png"], map(f"{stem}_{{}}.png".format, itertools.count(2)))


def _write_new(png: bytes, folder: Path, now: datetime.datetime) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    names = save_names(now)
    while True:
        path = folder / next(names)
        try:
            with path.open("xb") as f:
                f.write(png)
        except FileExistsError:
            continue
        return path


def save_flow(png: bytes, folder: Path, now: datetime.datetime) -> Outcome:
    """F17-1, F17-4: write ``png`` into ``folder`` under a new name; the PNG goes to the clipboard either way."""
    try:
        path = _write_new(png, folder, now)
    except OSError as err:
        _log.warning("screenshot not saved: %s", type(err).__name__)
        return Outcome(ClipboardPng(png), save_failed_notice(folder, err.strerror or type(err).__name__), None)
    return Outcome(ClipboardPng(png), save_ok_notice(path), None)
