"""The gui-mac lane's precondition: screen recording for the terminal (M9 WI-15, PRD F23-3).

Without it a capture is only the wallpaper, so ``require_screen_recording``
FAILS, never skips, with the same directions as the user-facing notice.
"""

from __future__ import annotations

import pytest

from snapocr.actions.messages import screen_permission_notice
from snapocr.gui.platform.mac.permission import screen_capture_allowed

SCREEN_RECORDING_HELP = "gui-mac needs the screen-recording permission. " + screen_permission_notice().body.splitlines()[0]


def require_screen_recording() -> None:
    if not screen_capture_allowed():
        pytest.fail(SCREEN_RECORDING_HELP, pytrace=False)
