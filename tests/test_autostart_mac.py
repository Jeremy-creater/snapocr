"""M9 WI-12: the LaunchAgent for start at login on a Mac (PRD F23-7; M9 plan D19). Pure, both hosts.

Pinned here (beyond the plan text):
- ``launch_agent_args`` keeps ``executable`` exactly as given (a venv's python
  is a symlink; resolving it loses the venv) and makes the config path absolute
  and resolved, as the Windows command does.
- The plist is XML and holds exactly Label, ProgramArguments, RunAtLoad and
  ProcessType; the arguments are a list, so nothing is shell-quoted.
"""

import plistlib
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from snapocr.autostart import LAUNCH_AGENT_LABEL, launch_agent_args, launch_agent_plist


def test_the_label():
    assert LAUNCH_AGENT_LABEL == "io.github.jeremy-creater.snapocr"


def test_args_run_snapocr_on_the_config(tmp_path):
    python = tmp_path / "venv" / "bin" / ".." / "bin" / "python"
    config = tmp_path / "我的 \"配置\"" / "config.toml"
    assert launch_agent_args(python, config) == [str(python), "-m", "snapocr", "--config", str(config.resolve())]


def test_the_executable_is_not_resolved(tmp_path):
    real = tmp_path / "uv" / "python3.12"
    real.parent.mkdir()
    real.write_text("", encoding="utf-8")
    link = tmp_path / "venv-python"
    link.symlink_to(real)
    assert launch_agent_args(link, tmp_path / "c.toml")[0] == str(link)


def test_a_relative_config_becomes_absolute(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert launch_agent_args(Path("/usr/bin/python3"), Path("config.toml"))[-1] == str((tmp_path / "config.toml").resolve())


def test_the_plist_has_exactly_these_keys(tmp_path):
    args = launch_agent_args(Path("/Users/x/venv/bin/python"), tmp_path / "config.toml")
    data = launch_agent_plist(LAUNCH_AGENT_LABEL, args)
    assert data.startswith(b"<?xml")
    assert plistlib.loads(data) == {"Label": LAUNCH_AGENT_LABEL, "ProgramArguments": args, "RunAtLoad": True,
                                    "ProcessType": "Interactive"}


_TEXT = st.text(st.characters(blacklist_categories=("Cs", "Cc")), min_size=1)


@given(st.lists(_TEXT, min_size=1, max_size=6))
def test_any_arguments_round_trip(args):
    """S5: spaces, quotes, Chinese, ampersands come back unchanged."""
    assert plistlib.loads(launch_agent_plist(LAUNCH_AGENT_LABEL, args))["ProgramArguments"] == args


def test_the_packaged_app_runs_its_own_executable(tmp_path):
    # F24-3: a packaged app has no Python, and its executable takes --config directly.
    app = Path("/Applications/snapocr.app/Contents/MacOS/snapocr")
    config = tmp_path / "config.toml"
    assert launch_agent_args(app, config, frozen=True) == [str(app), "--config", str(config.resolve())]
