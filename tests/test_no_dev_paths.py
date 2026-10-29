"""M8 WI-4: no development-machine paths in the shipped code (PRD F21-4; CLAUDE.md paths).

Other people's computers have no ``D:\\DevLocal``; anything under ``src/`` that
names it is either a wrong default or a misleading hint.
"""

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
DEV_PATH = re.compile(r"[A-Za-z]:[\\/]+(DevLocal|LLM[\\/]+workspace)", re.IGNORECASE)


def test_src_names_no_development_paths():
    files = sorted(SRC.rglob("*.py"))
    assert len(files) > 50  # the scan really looked at the package
    hits = [
        f"{path.relative_to(SRC)}:{number}: {line.strip()}"
        for path in files
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if DEV_PATH.search(line)
    ]
    assert hits == []


def test_the_pattern_catches_both_slashes():
    assert DEV_PATH.search(r"D:\DevLocal\envs") and DEV_PATH.search("d:/devlocal/runtime")
    assert DEV_PATH.search(r"D:\\LLM\\workspace\\snapocr")
    assert not DEV_PATH.search("%LOCALAPPDATA%/snapocr")
