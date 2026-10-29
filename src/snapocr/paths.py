"""Where the config file and the runtime data live (PRD F21-1, F21-2, F23-6).

Pure: the environment, the home directory, the file checks and the platform
come in as arguments, so nothing here reads the real ``%APPDATA%`` (CLAUDE.md,
M8 plan D6, M9 plan D6). On a Mac the per-user places are under ``~/Library``,
and ``APPDATA`` / ``LOCALAPPDATA`` mean nothing.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path

from snapocr.hotkeys import check_platform

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
    platform: str = "win32",
) -> Path:
    """F21-1: the argument, ``SNAPOCR_CONFIG``, the checkout's file, then the per-user file."""
    user_dir = _user_dir(env, home, check_platform(platform), "APPDATA", ("AppData", "Roaming"),
                         ("Library", "Application Support"))
    if arg is not None:
        return arg
    value = env.get(CONFIG_ENV, "").strip()
    if value:
        return Path(value)
    if source_root is not None and exists(source_root / SOURCE_CONFIG_NAME):
        return source_root / SOURCE_CONFIG_NAME
    return user_dir / APP_DIR_NAME / USER_CONFIG_NAME


def _user_dir(env: Mapping[str, str], home: Path, platform: str, variable: str,
              windows: tuple[str, ...], mac: tuple[str, ...]) -> Path:
    if platform == "darwin":
        return home.joinpath(*mac)
    return _env_dir(env, variable, home, *windows)


def runtime_dir(env: Mapping[str, str], *, home: Path, platform: str = "win32") -> tuple[Path, str | None]:
    """F21-2: an absolute ``SNAPOCR_RUNTIME_DIR``, else the per-user default; plus why the variable was refused.

    The default is ``%LOCALAPPDATA%/snapocr`` on Windows, ``~/Library/Logs/snapocr`` on a Mac (F23-6).
    """
    default = _user_dir(env, home, check_platform(platform), "LOCALAPPDATA", ("AppData", "Local"),
                        ("Library", "Logs")) / APP_DIR_NAME
    value = env.get(RUNTIME_ENV, "").strip()
    if not value:
        return default, None
    if Path(value).is_absolute():
        return Path(value), None
    return default, f"不是绝对路径（{value}），日志和 debug 文件改放 {default}"
