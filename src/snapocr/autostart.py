"""The command line registered for start at login (PRD F11-6, M3 plan D8). Stdlib only."""

from __future__ import annotations

import subprocess
from pathlib import Path


def autostart_command(executable: Path, config_path: Path, frozen: bool = False) -> str:
    """``pythonw.exe`` next to ``executable`` (no console window) running snapocr on ``config_path``.

    The packaged build (``frozen``, PRD F22-2) has no Python next to it: ``executable`` is
    ``snapocr.exe`` itself.
    """
    config = Path(config_path).resolve()
    if frozen:
        return subprocess.list2cmdline([str(executable), "--config", str(config)])
    pythonw = Path(executable).with_name("pythonw.exe")
    return subprocess.list2cmdline([str(pythonw), "-m", "snapocr", "--config", str(config)])
