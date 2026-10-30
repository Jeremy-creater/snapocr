"""M9 WI-13: start at login through a LaunchAgent file (gui-mac lane; PRD F23-7, plan D19).

Every test writes into ``tmp_path``; the module fixture checks that the real
``~/Library/LaunchAgents/<label>.plist`` is neither created, changed nor
removed while these run (CLAUDE.md).

Pinned here (beyond the plan text):
- Switching on writes the WI-12 plist; ``plutil -lint`` accepts it.
- On twice gives the same bytes and one file; off twice is harmless.
- An unwritable directory is an ``OSError`` and leaves no file, temporary or not.
- ``launchctl`` is never run: the file takes effect at the next login.
"""

import plistlib
import subprocess
from pathlib import Path

import pytest

from snapocr.autostart import LAUNCH_AGENT_LABEL, launch_agent_args, launch_agent_plist
from snapocr.gui.platform.mac import kit
from snapocr.gui.platform.mac.autostart import LaunchAgentAutostart

pytestmark = pytest.mark.gui

REAL = Path.home() / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist"
ARGS = ["/Users/x/venv/bin/python", "-m", "snapocr", "--config", "/Users/x/我的 配置/config.toml"]


def _state(path: Path):
    return (path.exists(), path.stat().st_mtime_ns if path.exists() else None)


@pytest.fixture(scope="module", autouse=True)
def real_launch_agent_untouched():
    before = _state(REAL)
    yield
    assert _state(REAL) == before, f"{REAL} changed during the tests"


def test_on_writes_the_plist_and_off_removes_it(tmp_path):
    agent = LaunchAgentAutostart(ARGS, directory=tmp_path / "LaunchAgents")
    assert agent.is_enabled() is False
    agent.set_enabled(True)
    path = tmp_path / "LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist"
    assert agent.is_enabled() is True
    assert path.read_bytes() == launch_agent_plist(LAUNCH_AGENT_LABEL, ARGS)
    assert subprocess.run(["plutil", "-lint", str(path)], capture_output=True).returncode == 0
    agent.set_enabled(False)
    assert agent.is_enabled() is False and not path.exists()


def test_on_twice_and_off_twice(tmp_path):
    agent = LaunchAgentAutostart(ARGS, directory=tmp_path)
    agent.set_enabled(True)
    first = (tmp_path / f"{LAUNCH_AGENT_LABEL}.plist").read_bytes()
    agent.set_enabled(True)
    assert [p.name for p in tmp_path.iterdir()] == [f"{LAUNCH_AGENT_LABEL}.plist"]
    assert (tmp_path / f"{LAUNCH_AGENT_LABEL}.plist").read_bytes() == first
    agent.set_enabled(False)
    agent.set_enabled(False)
    assert list(tmp_path.iterdir()) == []


def test_an_unwritable_directory_is_an_error_and_leaves_nothing(tmp_path):
    locked = tmp_path / "LaunchAgents"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        with pytest.raises(OSError):
            LaunchAgentAutostart(ARGS, directory=locked).set_enabled(True)
        assert list(locked.iterdir()) == []
    finally:
        locked.chmod(0o700)


def test_a_folder_in_the_way_is_an_error_and_leaves_no_temporary_file(tmp_path):
    (tmp_path / f"{LAUNCH_AGENT_LABEL}.plist" / "x").mkdir(parents=True)
    with pytest.raises(OSError):
        LaunchAgentAutostart(ARGS, directory=tmp_path).set_enabled(True)
    assert [p.name for p in tmp_path.iterdir()] == [f"{LAUNCH_AGENT_LABEL}.plist"]


def test_another_label_is_another_file(tmp_path):
    LaunchAgentAutostart(ARGS, directory=tmp_path, label="test.snapocr").set_enabled(True)
    assert [p.name for p in tmp_path.iterdir()] == ["test.snapocr.plist"]


def test_the_kit_runs_this_python_on_the_config(tmp_path):
    agent = kit.make_autostart(Path("/Users/x/venv/bin/python"), tmp_path / "config.toml", False, directory=tmp_path)
    agent.set_enabled(True)
    written = plistlib.loads((tmp_path / f"{LAUNCH_AGENT_LABEL}.plist").read_bytes())
    assert written["ProgramArguments"] == launch_agent_args(Path("/Users/x/venv/bin/python"), tmp_path / "config.toml")


def test_the_kit_defaults_to_the_users_launch_agents():
    """Read-only: whether it says on matches whether the real file is there."""
    assert kit.make_autostart(Path("/usr/bin/python3"), Path("c.toml"), False).is_enabled() is REAL.exists()


def test_kit_gives_the_packaged_app_a_command_without_python(tmp_path):
    app = Path("/Applications/snapocr.app/Contents/MacOS/snapocr")
    agent = kit.make_autostart(app, tmp_path / "config.toml", True, directory=tmp_path)
    agent.set_enabled(True)
    written = plistlib.loads((tmp_path / f"{LAUNCH_AGENT_LABEL}.plist").read_bytes())
    assert written["ProgramArguments"] == [str(app), "--config", str((tmp_path / "config.toml").resolve())]
