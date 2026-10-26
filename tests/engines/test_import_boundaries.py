"""Import isolation: engine-agnostic modules must not pull heavy runtime deps."""

import ast
import json
import subprocess
import sys
from pathlib import Path

HEAVY = ["rapidocr", "onnxruntime", "numpy", "cv2"]


def test_types_and_errors_import_no_heavy_deps():
    code = (
        "import json, sys\n"
        "import snapocr.engines.types, snapocr.engines.errors\n"
        f"heavy = {HEAVY!r}\n"
        "print(json.dumps([m for m in heavy if m in sys.modules]))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-I", "-c", code],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout.strip()) == []


# --- WI-6: the RapidOCR adapter is the only runtime importer -----------------

SRC = Path(__file__).resolve().parents[2] / "src" / "snapocr"
ADAPTER = "engines/rapidocr_engine.py"
RUNTIME = {"rapidocr", "onnxruntime"}


def _run_isolated(code: str) -> list[str]:
    proc = subprocess.run(
        [sys.executable, "-I", "-c", code],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])


def _imported_roots(tree: ast.AST) -> set[str]:
    roots = set()
    for node in ast.walk(tree):  # includes imports inside function bodies
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_only_adapter_imports_rapidocr_or_onnxruntime():
    files = sorted(SRC.rglob("*.py"))
    assert len(files) >= 6

    importers: dict[str, set[str]] = {name: set() for name in RUNTIME}
    for path in files:
        roots = _imported_roots(ast.parse(path.read_text(encoding="utf-8"), str(path)))
        for name in RUNTIME & roots:
            importers[name].add(path.relative_to(SRC).as_posix())

    assert importers["rapidocr"] == {ADAPTER}
    assert importers["onnxruntime"] <= {ADAPTER}


def test_import_engines_package_does_not_load_runtime():
    code = (
        "import json, sys\n"
        "import snapocr.engines, snapocr.engines.rapidocr_engine\n"
        f"heavy = {HEAVY!r}\n"
        "print(json.dumps([m for m in heavy if m in sys.modules]))\n"
    )
    assert _run_isolated(code) == []


def test_build_params_callable_without_loading_runtime():
    code = (
        "import json, sys\n"
        "from snapocr.engines.config import OcrEngineConfig, resolve_model_paths\n"
        "from snapocr.engines.rapidocr_engine import build_rapidocr_params\n"
        "d = build_rapidocr_params(resolve_model_paths(OcrEngineConfig()))\n"
        "assert d['Rec.model_path'].endswith('.onnx'), d\n"
        f"heavy = {HEAVY!r}\n"
        "print(json.dumps([m for m in heavy if m in sys.modules]))\n"
    )
    assert _run_isolated(code) == []


# --- F2 A4: postprocess depends only on the stdlib and engines.types ---------

POSTPROCESS = SRC / "postprocess"
POSTPROCESS_ALLOWED = {"snapocr.engines.types"}


def _imported_modules(tree: ast.AST) -> set[str]:
    modules = set()
    for node in ast.walk(tree):  # includes imports inside function bodies
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "relative imports are not used in snapocr"
            modules.add(node.module)
    return modules


def test_postprocess_imports_only_stdlib_and_types():
    files = sorted(POSTPROCESS.glob("*.py"))
    assert len(files) >= 6

    offending: dict[str, set[str]] = {}
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
        for module in _imported_modules(tree):
            root = module.split(".")[0]
            if root in sys.stdlib_module_names:
                continue
            if module in POSTPROCESS_ALLOWED or module.startswith("snapocr.postprocess."):
                continue
            offending.setdefault(path.name, set()).add(module)
    assert offending == {}

    code = (
        "import json, sys\n"
        "import snapocr.postprocess\n"
        "from snapocr.postprocess import postprocess, PostprocessOptions, RULE_ORDER\n"
        f"heavy = {HEAVY!r}\n"
        "print(json.dumps([m for m in heavy if m in sys.modules]))\n"
    )
    assert _run_isolated(code) == []


# --- F4 WI-6: only the translator transport speaks HTTP (D3) --------------------

HTTP_TRANSPORT = "translators/http_transport.py"
FORBIDDEN_HTTP = {"urllib.request", "requests", "httpx", "aiohttp", "urllib3"}


def _imported_names(tree: ast.AST) -> set[str]:
    """Absolute module names imported, including ``from pkg import mod`` as ``pkg.mod``."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def _src_imports() -> dict[str, set[str]]:
    return {
        path.relative_to(SRC).as_posix(): _imported_names(
            ast.parse(path.read_text(encoding="utf-8"), str(path))
        )
        for path in sorted(SRC.rglob("*.py"))
    }


def _uses(names: set[str], module: str) -> bool:
    return any(n == module or n.startswith(module + ".") for n in names)


def test_only_http_transport_imports_http_client():
    importers = {f for f, names in _src_imports().items() if _uses(names, "http.client")}
    assert importers == {HTTP_TRANSPORT}


def test_no_module_imports_urllib_request_or_http_libs():
    offenders = {
        f: sorted(m for m in FORBIDDEN_HTTP if _uses(names, m))
        for f, names in _src_imports().items()
    }
    assert {f: m for f, m in offenders.items() if m} == {}


def test_http_import_scan_positive_control():
    for source in ["import http.client", "from http import client", "from http.client import HTTPConnection"]:
        assert _uses(_imported_names(ast.parse(source)), "http.client"), source
    for source in ["from urllib import request", "import urllib.request", "import requests"]:
        names = _imported_names(ast.parse(source))
        assert any(_uses(names, m) for m in FORBIDDEN_HTTP), source
    assert not _uses(_imported_names(ast.parse("import http")), "http.client")


# --- F4 WI-7: snapocr.translators depends on stdlib, chars and itself only ------

import importlib.util  # noqa: E402

TRANSLATORS_PKG = "snapocr.translators"
CHARS = "snapocr.postprocess.chars"


def _within(name: str, package: str) -> bool:
    return name == package or name.startswith(package + ".")


def _translators_violations(source: str, package: str = TRANSLATORS_PKG) -> list[str]:
    """Imports that are neither stdlib, ``snapocr.postprocess.chars`` nor the package itself.

    Relative imports are resolved first (M7); ``from pkg import name`` is also
    judged as ``pkg.name`` so ``from snapocr.postprocess import chars`` is legal.
    """
    bad = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            pairs = [(alias.name, [alias.name]) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = importlib.util.resolve_name("." * node.level + (node.module or ""), package)
            pairs = [(base, [base, f"{base}.{alias.name}"]) for alias in node.names]
        else:
            continue
        for base, candidates in pairs:
            ok = (
                base.split(".")[0] in sys.stdlib_module_names
                or _within(base, TRANSLATORS_PKG)
                or any(c == CHARS for c in candidates)
            )
            if not ok:
                bad.append(candidates[-1])
    return bad


def test_translators_import_only_stdlib_chars_and_self():
    files = sorted((SRC / "translators").glob("*.py"))
    assert len(files) >= 7
    violations = {
        path.name: _translators_violations(path.read_text(encoding="utf-8"))
        for path in files
    }
    assert {name: v for name, v in violations.items() if v} == {}


def test_translators_boundary_checker_positive_control():
    for source in [
        "from ..engines import base",
        "from .. import engines",
        "import numpy",
        "from snapocr.postprocess import normalize",
    ]:
        assert _translators_violations(source), source
    for source in [
        "from snapocr.postprocess import chars",
        "from snapocr.postprocess.chars import is_cjk",
        "from .errors import X",
        "import json",
        "from __future__ import annotations",
    ]:
        assert _translators_violations(source) == [], source


def test_import_translators_loads_no_heavy_deps():
    code = (
        "import json, pkgutil, importlib, sys\n"
        "import snapocr.translators as pkg\n"
        "for m in pkgutil.iter_modules(pkg.__path__):\n"
        "    importlib.import_module('snapocr.translators.' + m.name)\n"
        f"heavy = {HEAVY + ['snapocr.engines.rapidocr_engine']!r}\n"
        "print(json.dumps([m for m in heavy if m in sys.modules]))\n"
    )
    assert _run_isolated(code) == []


# --- M2 WI-8: actions and the pure-logic modules stay free of Qt, ctypes and OCR runtime ---

GUI_FREE = ["actions", "hotkeys.py", "geometry.py", "config", "commands.py"]
FORBIDDEN = {"PySide6", "shiboken6", "ctypes", "rapidocr", "onnxruntime"}


def _gui_free_files() -> list[Path]:
    files = []
    for name in GUI_FREE:
        target = SRC / name
        files += sorted(target.rglob("*.py")) if target.is_dir() else [target]
    return files


def test_gui_free_modules_do_not_import_qt_ctypes_or_runtime():
    files = _gui_free_files()
    assert len(files) >= 10
    offenders = {
        path.relative_to(SRC).as_posix(): sorted(roots & FORBIDDEN)
        for path in files
        if (roots := _imported_roots(ast.parse(path.read_text(encoding="utf-8"), str(path)))) & FORBIDDEN
    }
    assert offenders == {}


def test_importing_gui_free_modules_loads_none_of_them():
    modules = sorted(
        "snapocr." + p.relative_to(SRC).with_suffix("").as_posix().replace("/", ".").removesuffix(".__init__")
        for p in _gui_free_files()
    )
    code = (
        "import importlib, json, sys\n"
        f"for m in {modules!r}: importlib.import_module(m)\n"
        f"print(json.dumps(sorted({{m.split('.')[0] for m in sys.modules}} & set({sorted(FORBIDDEN)!r}))))\n"
    )
    assert _run_isolated(code) == []


# --- WI-19: ctypes only under snapocr/gui/platform ----------------------------------------


def test_ctypes_only_in_gui_platform():
    offenders = []
    for path in SRC.rglob("*.py"):
        rel = path.relative_to(SRC).as_posix()
        if rel.startswith("gui/platform/"):
            continue
        if "ctypes" in _imported_roots(ast.parse(path.read_text(encoding="utf-8"))):
            offenders.append(rel)
    assert offenders == []
