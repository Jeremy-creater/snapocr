"""FIX-2: hypothesis example budget per run (CLAUDE.md, 2026-10-26).

Every lane loads the ``unit`` profile (50 examples) from ``tests/conftest.py``;
``--hypothesis-profile=thorough`` (200 examples) is for manual runs. A test's
own ``@settings(max_examples=...)`` still wins. The checks below follow the
profile actually requested, so they also pass in a thorough run.
"""

import subprocess
import sys
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[1]
BUDGET = {"unit": 50, "thorough": 200}


def _requested(config) -> str:
    return config.getoption("hypothesis_profile") or "unit"


def test_profiles_are_registered():
    assert settings.get_profile("unit").max_examples == 50
    assert settings.get_profile("thorough").max_examples == 200


def test_active_profile_budget(request):
    assert settings.default.max_examples == BUDGET[_requested(request.config)]


def test_unannotated_given_runs_the_active_budget(request):
    runs = []

    @settings(database=None)  # a saved failing example would add runs
    @given(st.integers())
    def inner(n):
        runs.append(n)

    inner()
    assert len(runs) == BUDGET[_requested(request.config)]


def test_explicit_max_examples_beats_the_profile():
    runs = []

    @settings(max_examples=7, database=None)
    @given(st.integers())
    def inner(n):
        runs.append(n)

    inner()
    assert len(runs) == 7


def test_thorough_profile_is_selectable_from_the_command_line():
    """Both budget checks compare against BUDGET[requested], so a broken override fails them."""
    module = "tests/test_hypothesis_profile.py"
    nodes = [f"{module}::test_active_profile_budget", f"{module}::test_unannotated_given_runs_the_active_budget"]
    for extra in ([], ["--hypothesis-profile=thorough"]):
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", *nodes, "-q", "-p", "no:cacheprovider", *extra],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=ROOT,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "2 passed" in proc.stdout
