"""M9 WI-9: only the allowed places read ``sys.platform`` (CLAUDE.md; M9 plan D6).

Pure logic takes ``platform`` as a parameter so tests can run both systems on
either host. ``sys.platform`` may be read only in ``snapocr/gui/platform/**``
and in the thin functions that read the real environment anyway:
``config/files.default_config_path`` and, in ``app.py``, ``DEFAULT_LOG_DIR``
and ``runtime_issues``. A read is placed by its enclosing function, or by the
name a module-level statement assigns.
"""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "snapocr"

ALLOWED = {
    ("config/files.py", "default_config_path"),
    ("app.py", "DEFAULT_LOG_DIR"),
    ("app.py", "runtime_issues"),
}


def _is_sys_platform(node: ast.AST) -> bool:
    return (isinstance(node, ast.Attribute) and node.attr == "platform"
            and isinstance(node.value, ast.Name) and node.value.id == "sys")


def _reads(tree: ast.Module):
    """(place, line) of each ``sys.platform`` read; place is the function, or the assigned module name."""
    for top in tree.body:
        if isinstance(top, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            place = top.name
        elif isinstance(top, ast.Assign) and isinstance(top.targets[0], ast.Name):
            place = top.targets[0].id
        else:
            place = "<module>"
        for node in ast.walk(top):
            if _is_sys_platform(node):
                yield place, node.lineno


def platform_reads(root: Path = SRC) -> set[tuple[str, str, int]]:
    found = set()
    for path in root.rglob("*.py"):
        rel = path.relative_to(root).as_posix()
        for place, line in _reads(ast.parse(path.read_text(encoding="utf-8"))):
            found.add((rel, place, line))
    return found


def test_only_the_allowed_places_read_sys_platform():
    outside = {(f, place, line) for f, place, line in platform_reads()
               if not f.startswith("gui/platform/") and (f, place) not in ALLOWED}
    assert outside == set()


def test_every_allowed_place_still_reads_it():
    """A stale entry would let a later read in that place through unnoticed."""
    assert {(f, place) for f, place, _ in platform_reads()} >= ALLOWED


def test_the_scan_finds_reads(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "m.py").write_text(
        "import sys\nX = sys.platform\ndef f():\n    return sys.platform == 'darwin'\nclass C:\n"
        "    p = sys.platform\nif sys.platform:\n    pass\nplatform = 'win32'\n",
        encoding="utf-8",
    )
    assert platform_reads(tmp_path) == {("pkg/m.py", "X", 2), ("pkg/m.py", "f", 4), ("pkg/m.py", "C", 6),
                                        ("pkg/m.py", "<module>", 7)}
