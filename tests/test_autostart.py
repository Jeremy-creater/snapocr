"""M3 WI-3: the command line written for start at login (PRD F11-6; M3 plan D8).

Pinned here:
- The interpreter is ``pythonw.exe`` next to the running one (no console
  window), whether snapocr runs under ``python.exe`` or ``pythonw.exe``.
- The config path is made absolute; paths with spaces are quoted.
"""

from pathlib import Path

from snapocr.autostart import autostart_command


def test_python_becomes_pythonw():
    cmd = autostart_command(Path(r"D:\DevLocal\envs\snapocr\Scripts\python.exe"), Path(r"D:\LLM\workspace\snapocr\config.local.toml"))
    assert cmd == r"D:\DevLocal\envs\snapocr\Scripts\pythonw.exe -m snapocr --config D:\LLM\workspace\snapocr\config.local.toml"


def test_pythonw_stays():
    cmd = autostart_command(Path(r"D:\envs\x\Scripts\pythonw.exe"), Path(r"D:\c.toml"))
    assert cmd == r"D:\envs\x\Scripts\pythonw.exe -m snapocr --config D:\c.toml"


def test_spaces_are_quoted():
    cmd = autostart_command(Path(r"C:\Program Files\Py\python.exe"), Path(r"D:\my configs\c.toml"))
    assert cmd == r'"C:\Program Files\Py\pythonw.exe" -m snapocr --config "D:\my configs\c.toml"'


def test_relative_config_becomes_absolute(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cmd = autostart_command(Path(r"D:\py\python.exe"), Path("c.toml"))
    assert cmd.endswith(f" --config {tmp_path / 'c.toml'}") or cmd.endswith(f' --config "{tmp_path / "c.toml"}"')
    assert str(tmp_path / "c.toml") in cmd
