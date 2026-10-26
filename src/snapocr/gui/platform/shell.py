"""Open a file with its default program (F9-1 "打开配置文件")."""

from __future__ import annotations

import os
from pathlib import Path


def open_file(path: Path) -> None:
    """Raises ``OSError`` when Windows cannot open it (missing file, no associated program)."""
    os.startfile(path)  # noqa: S606 - the user's own config file
