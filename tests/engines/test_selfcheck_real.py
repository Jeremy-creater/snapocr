"""M8 WI-15: ``snapocr --self-check`` with the real models (PRD F22-4, engine lane).

This is the path the release workflow runs against the packaged exe: the entry point
with ``--self-check`` recognizes a fixture offline, writes the report, and neither
starts the GUI nor creates a config file.
"""

import json
from pathlib import Path

import pytest

import snapocr


pytestmark = pytest.mark.engine

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "en.png"


def test_self_check_recognizes_a_fixture_offline(no_network, real_model_paths, tmp_path, monkeypatch):
    if not FIXTURE.is_file():
        pytest.fail(f"missing test fixture {FIXTURE}; regenerate with tests/fixtures/make_fixtures.ps1")
    home = tmp_path / "home"
    monkeypatch.setenv("APPDATA", str(home / "Roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(home / "Local"))
    report = tmp_path / "out" / "report.json"

    from snapocr.__main__ import main  # imported late: runpy in test_app warns if collection imported it

    code = main(["snapocr", "--self-check", str(FIXTURE), str(report)])

    data = json.loads(report.read_text(encoding="utf-8"))
    assert code == 0, data
    assert data["ok"] is True and data["version"] == snapocr.__version__ and data["error"] == ""
    assert "quick brown fox" in data["text"]
    assert not home.exists()
    assert no_network.attempts == []
