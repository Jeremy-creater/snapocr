"""Where the config file and the runtime data live (PRD F21-1, F21-2).

Pure: the environment, the home directory and the file checks come in as
arguments, so nothing here reads the real ``%APPDATA%`` (CLAUDE.md, M8 plan D6).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path

CONFIG_ENV = "SNAPOCR_CONFIG"
RUNTIME_ENV = "SNAPOCR_RUNTIME_DIR"
SOURCE_CONFIG_NAME = "config.local.toml"
USER_CONFIG_NAME = "config.toml"
APP_DIR_NAME = "snapocr"


def source_root(module_file: Path, exists: Callable[[Path], bool]) -> Path | None:
    """The checkout root when running from ``<root>/src/snapocr/`` (an editable install), else None."""
    src = module_file.parent.parent
    root = src.parent
    if src.name == "src" and exists(root / "pyproject.toml"):
        return root
    return None


def _env_dir(env: Mapping[str, str], name: str, home: Path, *fallback: str) -> Path:
    value = env.get(name, "").strip()
    return Path(value) if value else home.joinpath(*fallback)


def find_config(
    arg: Path | None,
    env: Mapping[str, str],
    *,
    source_root: Path | None,
    exists: Callable[[Path], bool],
    home: Path,
) -> Path:
    """F21-1: the argument, ``SNAPOCR_CONFIG``, the checkout's file, then the per-user file."""
    if arg is not None:
        return arg
    value = env.get(CONFIG_ENV, "").strip()
    if value:
        return Path(value)
    if source_root is not None and exists(source_root / SOURCE_CONFIG_NAME):
        return source_root / SOURCE_CONFIG_NAME
    return _env_dir(env, "APPDATA", home, "AppData", "Roaming") / APP_DIR_NAME / USER_CONFIG_NAME
