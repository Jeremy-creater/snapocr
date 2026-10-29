"""M8 WI-1, WI-2: where the config file and the runtime data live (PRD F21-1, F21-2; M8 plan D6, D7).

Pinned here (beyond the plan text):
- ``find_config`` takes the first of: the ``--config`` argument, a non-blank
  ``SNAPOCR_CONFIG``, ``config.local.toml`` in the source root when it exists,
  ``%APPDATA%\\snapocr\\config.toml`` (``~/AppData/Roaming`` without ``APPDATA``).
  The file check is only asked about the source-root file.
- ``source_root`` is the directory above ``src/`` when the module sits in
  ``<root>/src/snapocr/`` and ``<root>/pyproject.toml`` exists; else ``None``.
"""

from pathlib import Path

import pytest

from snapocr.paths import find_config, source_root

HOME = Path("C:/Users/someone")
ROOT = Path("D:/code/snapocr")
APPDATA = {"APPDATA": "C:/Users/someone/AppData/Roaming"}
USER_FILE = Path("C:/Users/someone/AppData/Roaming/snapocr/config.toml")


def everything_exists(path: Path) -> bool:
    return True


def nothing_exists(path: Path) -> bool:
    return False


def find(arg=None, env=APPDATA, root=ROOT, exists=everything_exists):
    return find_config(arg, env, source_root=root, exists=exists, home=HOME)


# --- find_config -----------------------------------------------------------------


def test_the_argument_wins():
    env = APPDATA | {"SNAPOCR_CONFIG": "E:/env.toml"}
    assert find(Path("E:/arg.toml"), env) == Path("E:/arg.toml")


def test_the_environment_variable_comes_next():
    env = APPDATA | {"SNAPOCR_CONFIG": "E:/env.toml"}
    assert find(None, env) == Path("E:/env.toml")


@pytest.mark.parametrize("blank", ["", "   "])
def test_a_blank_environment_variable_does_not_count(blank):
    assert find(None, APPDATA | {"SNAPOCR_CONFIG": blank}) == ROOT / "config.local.toml"


def test_an_existing_source_root_file_comes_next():
    asked = []

    def exists(path):
        asked.append(path)
        return True

    assert find(exists=exists) == ROOT / "config.local.toml"
    assert asked == [ROOT / "config.local.toml"]


def test_a_missing_source_root_file_is_not_used():
    assert find(exists=nothing_exists) == USER_FILE


def test_no_source_root_means_the_user_file():
    assert find(root=None) == USER_FILE


def test_without_appdata_the_home_directory_is_used():
    assert find(env={}, root=None) == HOME / "AppData" / "Roaming" / "snapocr" / "config.toml"
    assert find(env={"APPDATA": ""}, root=None) == HOME / "AppData" / "Roaming" / "snapocr" / "config.toml"


# --- source_root -----------------------------------------------------------------


def test_source_root_of_an_editable_install():
    module = ROOT / "src" / "snapocr" / "paths.py"
    assert source_root(module, lambda p: p == ROOT / "pyproject.toml") == ROOT


def test_source_root_needs_pyproject():
    assert source_root(ROOT / "src" / "snapocr" / "paths.py", nothing_exists) is None


def test_an_installed_package_has_no_source_root():
    module = Path("C:/venv/Lib/site-packages/snapocr/paths.py")
    assert source_root(module, everything_exists) is None


def test_this_checkout_is_a_source_root():
    import snapocr.paths

    assert source_root(Path(snapocr.paths.__file__), Path.exists) == Path(__file__).resolve().parents[1]
