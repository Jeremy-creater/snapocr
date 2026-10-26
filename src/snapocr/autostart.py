"""The command line registered for start at login (PRD F11-6, M3 plan D8). Stdlib only."""

from __future__ import annotations

import subprocess
from pathlib import Path


def autostart_command(executable: Path, config_path: Path) -> str:
    """``pythonw.exe`` next to ``executable`` (no console window) running snapocr on ``config_path``."""
    pythonw = Path(executable).with_name("pythonw.exe")
    config = Path(config_path).resolve()
    return subprocess.list2cmdline([str(pythonw), "-m", "snapocr", "--config", str(config)])
