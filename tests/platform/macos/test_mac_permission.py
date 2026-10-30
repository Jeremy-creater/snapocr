"""M9 WI-15: the screen-recording permission on the real Mac (gui-mac lane; PRD F23-3, plan D15).

The path without the permission cannot be automated (``tccutil`` would change
Jeremy's settings); WI-25 checks it by hand.
"""

import time

import pytest

from snapocr.gui.platform.mac.permission import request_screen_capture, screen_capture_allowed
from support.mac_permissions import SCREEN_RECORDING_HELP, require_screen_recording

pytestmark = pytest.mark.gui


def test_the_lane_has_the_permission():
    require_screen_recording()
    assert screen_capture_allowed() is True


def test_request_when_already_allowed_returns_at_once():
    require_screen_recording()
    start = time.perf_counter()
    assert request_screen_capture() is True
    assert time.perf_counter() - start < 0.5  # no system prompt waiting for a click


def test_the_failure_says_where_to_turn_it_on():
    assert "系统设置 → 隐私与安全性 → 屏幕与系统录音" in SCREEN_RECORDING_HELP
    assert "终端" in SCREEN_RECORDING_HELP
