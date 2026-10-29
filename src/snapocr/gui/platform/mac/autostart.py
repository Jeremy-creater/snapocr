"""Start at login through a LaunchAgent file (PRD F23-7, M9 plan D19). Needs no admin rights.

Whether start at login is on is only whether the file exists. Switching on
writes the plist atomically (a temporary file in the same directory, then
``os.replace``), creating the directory when missing; switching off deletes it.
``launchctl`` is never run: loading the agent now would start a second
snapocr, and the file takes effect at the next login anyway.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Sequence
from pathlib import Path

from snapocr.autostart import LAUNCH_AGENT_LABEL, launch_agent_plist


def user_launch_agents() -> Path:
    return Path.home() / "Library" / "LaunchAgents"


class LaunchAgentAutostart:
    """``set_enabled`` raises ``OSError`` when the file cannot be written or removed."""

    def __init__(self, args: Sequence[str], *, directory: Path | None = None, label: str = LAUNCH_AGENT_LABEL) -> None:
        self._content = launch_agent_plist(label, list(args))
        self._path = Path(directory or user_launch_agents()) / f"{label}.plist"

    def is_enabled(self) -> bool:
        return self._path.exists()

    def set_enabled(self, enabled: bool) -> None:
        if not enabled:
            self._path.unlink(missing_ok=True)
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(dir=self._path.parent, prefix=".snapocr-", suffix=".plist")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(self._content)
            os.chmod(temp, 0o644)
            os.replace(temp, self._path)
        except BaseException:
            Path(temp).unlink(missing_ok=True)
            raise
