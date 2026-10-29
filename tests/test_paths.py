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
from hypothesis import given
from hypothesis import strategies as st

from snapocr.paths import find_config, runtime_dir, source_root

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


# --- runtime_dir (WI-2) ----------------------------------------------------------


def local(tmp_path):
    return {"LOCALAPPDATA": str(tmp_path / "Local")}


def test_runtime_dir_defaults_to_localappdata(tmp_path):
    assert runtime_dir(local(tmp_path), home=HOME) == (tmp_path / "Local" / "snapocr", None)


def test_runtime_dir_without_localappdata(tmp_path):
    assert runtime_dir({}, home=tmp_path) == (tmp_path / "AppData" / "Local" / "snapocr", None)


def test_an_absolute_runtime_variable_is_used_as_is(tmp_path):
    env = local(tmp_path) | {"SNAPOCR_RUNTIME_DIR": str(tmp_path / "runtime")}
    assert runtime_dir(env, home=HOME) == (tmp_path / "runtime", None)


@pytest.mark.parametrize("blank", ["", "  "])
def test_a_blank_runtime_variable_is_ignored_quietly(tmp_path, blank):
    env = local(tmp_path) | {"SNAPOCR_RUNTIME_DIR": blank}
    assert runtime_dir(env, home=HOME) == (tmp_path / "Local" / "snapocr", None)


def test_a_relative_runtime_variable_is_refused_with_a_reason(tmp_path):
    env = local(tmp_path) | {"SNAPOCR_RUNTIME_DIR": "logs"}
    default = tmp_path / "Local" / "snapocr"
    assert runtime_dir(env, home=HOME) == (default, f"不是绝对路径（logs），日志和 debug 文件改放 {default}")


# --- a Mac (M9 WI-9, PRD F23-6) ------------------------------------------------------------

MAC_HOME = Path("/Users/someone")
MAC_FILE = MAC_HOME / "Library" / "Application Support" / "snapocr" / "config.toml"
MAC_LOGS = MAC_HOME / "Library" / "Logs" / "snapocr"
WINDOWS_ENV = {"APPDATA": "/elsewhere/Roaming", "LOCALAPPDATA": "/elsewhere/Local"}  # set by hand, say


def mac_find(arg=None, env=WINDOWS_ENV, root=ROOT, exists=nothing_exists):
    return find_config(arg, env, source_root=root, exists=exists, home=MAC_HOME, platform="darwin")


def test_a_mac_keeps_the_user_file_in_application_support():
    assert mac_find() == MAC_FILE
    assert mac_find(env={}, root=None) == MAC_FILE


def test_a_mac_looks_in_the_same_order():
    assert mac_find(Path("/a/arg.toml"), WINDOWS_ENV | {"SNAPOCR_CONFIG": "/a/env.toml"}) == Path("/a/arg.toml")
    assert mac_find(None, {"SNAPOCR_CONFIG": "/a/env.toml"}, exists=everything_exists) == Path("/a/env.toml")
    assert mac_find(exists=everything_exists) == ROOT / "config.local.toml"


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        (WINDOWS_ENV, (MAC_LOGS, None)),
        (WINDOWS_ENV | {"SNAPOCR_RUNTIME_DIR": " "}, (MAC_LOGS, None)),
        (WINDOWS_ENV | {"SNAPOCR_RUNTIME_DIR": "/Users/someone/DevLocal/runtime/snapocr"},
         (Path("/Users/someone/DevLocal/runtime/snapocr"), None)),
        (WINDOWS_ENV | {"SNAPOCR_RUNTIME_DIR": "logs"}, (MAC_LOGS, f"不是绝对路径（logs），日志和 debug 文件改放 {MAC_LOGS}")),
    ],
)
def test_a_mac_keeps_runtime_data_in_library_logs(env, expected):
    assert runtime_dir(env, home=MAC_HOME, platform="darwin") == expected


def test_windows_is_the_default_platform():
    assert find_config(None, {}, source_root=None, exists=nothing_exists, home=HOME, platform="win32") == \
        find_config(None, {}, source_root=None, exists=nothing_exists, home=HOME)
    assert runtime_dir({}, home=HOME, platform="win32") == runtime_dir({}, home=HOME)


@pytest.mark.parametrize("call", [
    lambda: find_config(None, {}, source_root=None, exists=nothing_exists, home=HOME, platform="linux"),
    lambda: runtime_dir({}, home=HOME, platform="linux"),
])
def test_unknown_platform(call):
    with pytest.raises(ValueError, match="unknown platform"):
        call()


_SOURCES = st.sampled_from(["arg", "env", "root"])


@given(st.sets(_SOURCES), st.sampled_from(["win32", "darwin"]))
def test_the_first_available_source_wins(available, platform):
    """S4: whatever is given, the result is the first of argument, variable, checkout file, user file."""
    arg = Path("/a/arg.toml") if "arg" in available else None
    env = {"SNAPOCR_CONFIG": "/a/env.toml"} if "env" in available else {}
    exists = everything_exists if "root" in available else nothing_exists
    home = MAC_HOME if platform == "darwin" else HOME
    got = find_config(arg, env, source_root=ROOT, exists=exists, home=home, platform=platform)
    first = next((s for s in ("arg", "env", "root") if s in available), "user")
    user = MAC_FILE if platform == "darwin" else HOME / "AppData" / "Roaming" / "snapocr" / "config.toml"
    assert got == {"arg": Path("/a/arg.toml"), "env": Path("/a/env.toml"), "root": ROOT / "config.local.toml",
                   "user": user}[first]
