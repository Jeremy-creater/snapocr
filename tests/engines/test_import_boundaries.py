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
