"""M9 WI-11: single instance through ``fcntl.flock`` on a lock file (gui-mac lane; PRD F23-8, plan D18).

Every lock file lives under ``tmp_path``; the real ``$TMPDIR`` lock is never touched.

Pinned here:
- A second ``acquire`` of the same file, from this process or another, is None;
  after ``release`` the lock can be taken again.
- A holder killed with SIGKILL frees the lock; a stale file left on disk is no obstacle.
- Two lock files do not affect each other; a missing directory is created;
  ``release`` twice is fine.
"""

import os
import signal
import subprocess
import sys

import pytest

from snapocr.gui.platform.mac.single_instance import acquire

pytestmark = pytest.mark.gui

HOLDER = """
import sys
from snapocr.gui.platform.mac.single_instance import acquire
lock = acquire(sys.argv[1])
print("held" if lock else "busy", flush=True)
sys.stdin.read()
"""


@pytest.fixture
def holder():
    """Start a child process that takes the lock and keeps it until killed."""
    procs = []

    def start(lock_file):
        proc = subprocess.Popen(
            [sys.executable, "-c", HOLDER, str(lock_file)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
        )
        procs.append(proc)
        assert proc.stdout.readline().strip() == "held"
        return proc

    yield start
    for proc in procs:
        proc.kill()
        proc.wait(timeout=5)


def test_second_acquire_in_this_process_is_none_until_released(tmp_path):
    lock_file = tmp_path / "snapocr-a.lock"
    lock = acquire(lock_file)
    assert lock is not None
    assert acquire(lock_file) is None
    lock.release()
    again = acquire(lock_file)
    assert again is not None
    again.release()


def test_another_process_holding_the_lock_makes_it_none(tmp_path, holder):
    lock_file = tmp_path / "snapocr-a.lock"
    holder(lock_file)
    assert acquire(lock_file) is None


def test_a_killed_holder_frees_the_lock(tmp_path, holder):
    lock_file = tmp_path / "snapocr-a.lock"
    proc = holder(lock_file)
    os.kill(proc.pid, signal.SIGKILL)
    proc.wait(timeout=5)
    assert lock_file.exists()
    lock = acquire(lock_file)
    assert lock is not None
    lock.release()


def test_a_stale_lock_file_nobody_holds_is_taken(tmp_path):
    lock_file = tmp_path / "snapocr-a.lock"
    lock_file.write_text("left over")
    lock = acquire(lock_file)
    assert lock is not None
    lock.release()


def test_two_lock_files_do_not_affect_each_other(tmp_path):
    a = acquire(tmp_path / "snapocr-a.lock")
    b = acquire(tmp_path / "snapocr-b.lock")
    assert a is not None and b is not None
    a.release()
    b.release()


def test_a_missing_directory_is_created(tmp_path):
    lock_file = tmp_path / "new" / "dir" / "snapocr-a.lock"
    lock = acquire(lock_file)
    assert lock is not None
    assert lock_file.is_file()
    lock.release()


def test_release_twice_is_fine_and_frees_the_lock(tmp_path):
    lock_file = tmp_path / "snapocr-a.lock"
    lock = acquire(lock_file)
    lock.release()
    lock.release()
    again = acquire(lock_file)
    assert again is not None
    again.release()


def test_a_lock_file_that_cannot_be_created_is_an_error(tmp_path):
    locked = tmp_path / "ro"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        with pytest.raises(OSError):
            acquire(locked / "snapocr-a.lock")
        assert list(locked.iterdir()) == []
    finally:
        locked.chmod(0o700)
