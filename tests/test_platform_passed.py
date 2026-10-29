"""M9 WI-7: calls that depend on the platform pass it (PRD F23; M9 plan D6).

The ``platform`` parameters default to ``"win32"``, so a call on a Mac that
leaves it out silently follows Windows rules: the hotkey notices said
"错误码 -9878" and "Win+S" that way. This scans ``src/`` and fails on every
call to one of these functions without ``platform=``. The few calls where the
platform makes no difference are listed with the reason.
"""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "snapocr"

NEEDS_PLATFORM = {
    "parse_hotkey", "format_hotkey", "display_hotkey", "hotkey_taken", "register_all",
    "hotkey_failure_line", "hotkey_failed_notice", "settings_problem_text",
    "build_tray_menu", "update_tray_menu", "template", "load_config_file", "build_config",
    "changes", "write_changes", "font_families", "TranslationPopup", "AppController",
    "HotkeyEdit", "SettingsWindow",
}

# (file relative to src/snapocr, function) -> why the default is right there.
NO_PLATFORM_NEEDED = {
    ("config/schema.py", "parse_hotkey"): "the defaults Alt+1..6 parse the same on both systems",
}


def calls_without_platform():
    found = set()
    for path in SRC.rglob("*.py"):
        rel = path.relative_to(SRC).as_posix()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
            if name not in NEEDS_PLATFORM:
                continue
            if any(k.arg == "platform" for k in node.keywords) or (name == "template" and node.args):
                continue
            found.add((rel, name, node.lineno))
    return found


def test_every_platform_call_passes_the_platform():
    missing = {(f, n, line) for f, n, line in calls_without_platform() if (f, n) not in NO_PLATFORM_NEEDED}
    assert missing == set()


def test_the_exceptions_are_still_there():
    """A stale entry would hide a later call in the same file."""
    assert {(f, n) for f, n, _ in calls_without_platform()} >= set(NO_PLATFORM_NEEDED)


def test_the_scan_sees_a_missing_platform(tmp_path, monkeypatch):
    (tmp_path / "x.py").write_text("format_hotkey(h)\nformat_hotkey(h, platform=p)\nobj.register_all(b, r)\n"
                                   "template('darwin')\ntemplate()\n", encoding="utf-8")
    monkeypatch.setattr(__import__(__name__), "SRC", tmp_path)
    assert calls_without_platform() == {("x.py", "format_hotkey", 1), ("x.py", "register_all", 3),
                                        ("x.py", "template", 5)}
