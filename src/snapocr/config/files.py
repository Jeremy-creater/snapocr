"""Reading the config file and creating it (and its directory) from the template (PRD F9-1 to F9-3, F21-3).

Never raises for file problems: each becomes one ``ConfigIssue`` and the
defaults are used. A missing file is created with exclusive creation, so an
existing file is never overwritten; a broken file is never changed.
"""

from __future__ import annotations

import hashlib
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from snapocr.config.load import build_config
from snapocr.config.schema import AppConfig, ConfigIssue
from snapocr.config.template import template
from snapocr.paths import find_config, source_root


@dataclass(frozen=True)
class LoadResult:
    config: AppConfig
    issues: list[ConfigIssue]
    created: bool


def instance_key(path: Path) -> str:
    """12 hex digits naming the single instance of a config file (plan D5, M9 D18).

    One instance per config file: the default file behaves as a global single
    instance, while gui-lane runs on a temporary config never clash with it.
    Windows paths ignore case, so the resolved path is case-folded first.
    """
    key = os.path.normcase(str(Path(path).resolve()))
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def instance_name(path: Path) -> str:
    """The Windows single-instance mutex name for a config file."""
    return "Local\\snapocr-" + instance_key(path)


def lock_path(path: Path, lock_dir: Path) -> Path:
    """The Mac single-instance lock file for a config file, inside ``lock_dir`` (F23-8)."""
    return Path(lock_dir) / f"snapocr-{instance_key(path)}.lock"


def default_config_path() -> Path:
    """The config file when no ``--config`` is given (F21-1), from the real environment."""
    import snapocr.paths

    root = source_root(Path(snapocr.paths.__file__).resolve(), Path.exists)
    return find_config(None, os.environ, source_root=root, exists=Path.exists, home=Path.home())


def _defaults(path: Path, reason: str) -> LoadResult:
    return LoadResult(AppConfig(), [ConfigIssue(path, "", f"{reason}; using defaults")], created=False)


def load_config_file(path: Path, *, platform: str = "win32") -> LoadResult:
    """Read ``path`` for ``platform`` (M9 WI-5); a missing file gets that platform's template."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)  # first run: %APPDATA%/snapocr (F21-3)
    except OSError as e:
        return _defaults(path, f"could not create the config directory ({e.strerror or e})")
    try:
        # "x": fails if the file appeared in the meantime, so nothing is overwritten.
        with open(path, "x", encoding="utf-8", newline="\n") as f:
            f.write(template(platform))
    except FileExistsError:
        pass
    except OSError as e:
        # Windows reports a directory in the way as PermissionError; reading reports it below.
        if not path.exists():
            return _defaults(path, f"could not create the default config file ({e.strerror or e})")
    else:
        return LoadResult(AppConfig(), [], created=True)

    try:
        raw = path.read_bytes()
    except OSError as e:
        return _defaults(path, f"could not read the file ({e.strerror or e})")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        return _defaults(path, f"not valid UTF-8 (byte {e.start}); the file was not changed")
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        return _defaults(path, f"TOML syntax error: {e}; the file was not changed")
    config, issues = build_config(data, source=path, platform=platform)
    return LoadResult(config, issues, created=False)
