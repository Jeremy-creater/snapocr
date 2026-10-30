"""What start at login runs (PRD F11-6, F23-7; M3 plan D8, M9 plan D19). Stdlib only."""

from __future__ import annotations

import plistlib
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


# --- macOS: a LaunchAgent in ~/Library/LaunchAgents (PRD F23-7, M9 plan D19) --------------------

LAUNCH_AGENT_LABEL = "io.github.jeremy-creater.snapocr"


def launch_agent_args(executable: Path, config_path: Path, frozen: bool = False) -> list[str]:
    """``executable`` exactly as given (a venv's python is a symlink; resolving it loses the venv).

    The packaged app (``frozen``, PRD F24-3) has no Python: ``executable`` is the app's own binary.
    """
    module = [] if frozen else ["-m", "snapocr"]
    return [str(executable), *module, "--config", str(Path(config_path).resolve())]


def launch_agent_plist(label: str, args: list[str]) -> bytes:
    """The LaunchAgent file: run ``args`` at login as an interactive (foreground-priority) process."""
    plist = {"Label": label, "ProgramArguments": list(args), "RunAtLoad": True, "ProcessType": "Interactive"}
    return plistlib.dumps(plist, fmt=plistlib.FMT_XML)
