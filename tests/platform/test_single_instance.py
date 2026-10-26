"""M2 WI-19: single instance via a named mutex (gui lane; PRD F5-4; plan D5).

Pinned here:
- ``acquire(name)`` returns an ``InstanceLock``, or None when the name is
  already held (by this or another process). ``release()`` frees it and may
  be called twice. A held lock is freed by the kernel when its process exits.
- A name the kernel rejects (a backslash after the namespace prefix) raises ``OSError``.
"""

import subprocess
import sys
import uuid

import pytest

from snapocr.gui.platform.single_instance import acquire

pytestmark = pytest.mark.gui

HOLDER = """
import sys
from snapocr.gui.platform.single_instance import acquire
lock = acquire(sys.argv[1])
print("held" if lock else "busy", flush=True)
sys.stdin.readline()
"""


def unique_name() -> str:
    return f"Local\\snapocr-test-{uuid.uuid4().hex[:12]}"


def test_second_acquire_in_the_same_process_fails():
    name = unique_name()
    first = acquire(name)
    assert first is not None
    try:
        assert acquire(name) is None
    finally:
        first.release()


def test_release_frees_the_name_and_is_idempotent():
    name = unique_name()
    lock = acquire(name)
    lock.release()
    lock.release()
    again = acquire(name)
    assert again is not None
    again.release()


def test_another_process_holding_the_name_blocks_us_until_it_exits():
    name = unique_name()
    child = subprocess.Popen([sys.executable, "-c", HOLDER, name], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == "held"
        assert acquire(name) is None
    finally:
        child.communicate("\n", timeout=10)
    lock = acquire(name)
    assert lock is not None
    lock.release()


def test_name_rejected_by_the_kernel_raises():
    with pytest.raises(OSError):
        acquire("Local\\snapocr\\nested")  # ERROR_PATH_NOT_FOUND
