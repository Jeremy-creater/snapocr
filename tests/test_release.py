"""M8 WI-11: the release version is the same everywhere (PRD F21-10).

``pyproject.toml`` and ``snapocr.__version__`` give the version; ``CHANGELOG.md``
has a section for it and both READMEs install that tag. A release that bumps one
place and forgets another fails here before it is tagged.
"""

import re
import tomllib
from pathlib import Path

import snapocr

ROOT = Path(__file__).resolve().parents[1]
RELEASE = "0.2.0"


def _text(name: str) -> str:
    path = ROOT / name
    assert path.is_file(), f"{name} is missing from the repository root"
    return path.read_text(encoding="utf-8")


def test_the_package_and_pyproject_give_the_release_version():
    project = tomllib.loads(_text("pyproject.toml"))["project"]
    assert project["version"] == RELEASE
    assert snapocr.__version__ == RELEASE


def test_the_changelog_starts_with_the_release():
    headings = re.findall(r"^## \[?v?(\d+\.\d+\.\d+)\]?", _text("CHANGELOG.md"), re.MULTILINE)
    assert headings[:1] == [RELEASE]


def test_both_readmes_install_the_release_tag():
    pinned = f"git+https://github.com/Jeremy-creater/snapocr@v{RELEASE}"
    for name in ("README.md", "README.zh-CN.md"):
        assert pinned in _text(name), name
