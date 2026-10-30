"""M3 WI-3: the command line written for start at login (PRD F11-6; M3 plan D8).

Pinned here:
- The interpreter is ``pythonw.exe`` next to the running one (no console
  window), whether snapocr runs under ``python.exe`` or ``pythonw.exe``.
- The config path is made absolute; paths with spaces are quoted.
"""

from pathlib import Path

import pytest

from snapocr.autostart import autostart_command


@pytest.mark.windows  # the Run-key command line; the Mac counterpart is a LaunchAgent (M9 WI-12)
def test_python_becomes_pythonw():
    cmd = autostart_command(Path(r"D:\DevLocal\envs\snapocr\Scripts\python.exe"), Path(r"D:\LLM\workspace\snapocr\config.local.toml"))
    assert cmd == r"D:\DevLocal\envs\snapocr\Scripts\pythonw.exe -m snapocr --config D:\LLM\workspace\snapocr\config.local.toml"


@pytest.mark.windows  # the Run-key command line; the Mac counterpart is a LaunchAgent (M9 WI-12)
def test_pythonw_stays():
    cmd = autostart_command(Path(r"D:\envs\x\Scripts\pythonw.exe"), Path(r"D:\c.toml"))
    assert cmd == r"D:\envs\x\Scripts\pythonw.exe -m snapocr --config D:\c.toml"


@pytest.mark.windows  # the Run-key command line; the Mac counterpart is a LaunchAgent (M9 WI-12)
def test_spaces_are_quoted():
    cmd = autostart_command(Path(r"C:\Program Files\Py\python.exe"), Path(r"D:\my configs\c.toml"))
    assert cmd == r'"C:\Program Files\Py\pythonw.exe" -m snapocr --config "D:\my configs\c.toml"'


def test_relative_config_becomes_absolute(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cmd = autostart_command(Path(r"D:\py\python.exe"), Path("c.toml"))
    assert cmd.endswith(f" --config {tmp_path / 'c.toml'}") or cmd.endswith(f' --config "{tmp_path / "c.toml"}"')
    assert str(tmp_path / "c.toml") in cmd


# M8 WI-13 (PRD F22-2): the packaged build (sys.frozen) starts itself, not pythonw -m snapocr.


@pytest.mark.windows  # the Run-key command line; the Mac counterpart is a LaunchAgent (M9 WI-12)
def test_frozen_build_runs_its_own_exe():
    cmd = autostart_command(Path(r"D:\Apps\snapocr\snapocr.exe"), Path(r"C:\cfg\config.toml"), frozen=True)
    assert cmd == r"D:\Apps\snapocr\snapocr.exe --config C:\cfg\config.toml"


@pytest.mark.windows  # the Run-key command line; the Mac counterpart is a LaunchAgent (M9 WI-12)
def test_frozen_build_quotes_spaces():
    cmd = autostart_command(Path(r"C:\My Apps\snapocr\snapocr.exe"), Path(r"C:\my cfg\config.toml"), frozen=True)
    assert cmd == r'"C:\My Apps\snapocr\snapocr.exe" --config "C:\my cfg\config.toml"'


@pytest.mark.windows  # the Run-key command line; the Mac counterpart is a LaunchAgent (M9 WI-12)
def test_not_frozen_is_the_default():
    exe, cfg = Path(r"D:\py\python.exe"), Path(r"D:\c.toml")
    assert autostart_command(exe, cfg, frozen=False) == autostart_command(exe, cfg)
    assert autostart_command(exe, cfg) == r"D:\py\pythonw.exe -m snapocr --config D:\c.toml"
