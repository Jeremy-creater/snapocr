"""Build the Windows portable zip (PRD F22-1).

    python packaging/build.py --out D:\\DevLocal\\build\\snapocr

Runs PyInstaller with ``packaging/snapocr.spec`` (work files under ``<out>/work``), adds the
license files and ``README.txt`` next to ``snapocr.exe``, and writes
``<out>/snapocr-<version>-windows-x64.zip`` whose top level is the ``snapocr`` folder.
Prints the zip path on the last line.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import re
import shutil
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTRA_FILES = [ROOT / "LICENSE", ROOT / "THIRD_PARTY_NOTICES.md", ROOT / "packaging" / "README.txt"]
LICENSE_FILE = re.compile(r"^(LICEN[CS]E|COPYING|NOTICE|AUTHORS|ThirdPartyNotices)", re.IGNORECASE)


def version() -> str:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def runtime_distributions() -> list[importlib.metadata.Distribution]:
    """snapocr's installed runtime dependency tree (no extras), the packages the bundle carries."""
    found: dict[str, importlib.metadata.Distribution] = {}
    todo = ["snapocr"]
    while todo:
        name = re.split(r"[ ;<>=!~\[(]", todo.pop())[0].lower().replace("_", "-")
        if name in found:
            continue
        try:
            dist = importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError:  # a marker excluded it on this platform
            continue
        found[name] = dist
        todo += [r for r in dist.requires or [] if "extra ==" not in r]
    found.pop("snapocr")
    return [found[name] for name in sorted(found)]


def _license_files(dist: importlib.metadata.Distribution):
    """(target path, file): everything under ``licenses/`` (PEP 639) and license-looking files at
    the top of the dist-info folder; packages without any there (onnxruntime) keep theirs at the
    top of the package folder."""
    files = dist.files or []
    found = False
    for file in files:
        parts = file.parts
        if not parts[0].endswith(".dist-info"):
            continue
        inner = Path(*parts[1:])
        if inner.parts[0] == "licenses" or (len(inner.parts) == 1 and LICENSE_FILE.search(file.name)):
            found = True
            yield inner, file
    if not found:
        for file in files:
            if len(file.parts) == 2 and LICENSE_FILE.search(file.name):
                yield Path(file.name), file


def copy_licenses(dest: Path) -> int:
    """Each bundled package's license files, Python's, the PyInstaller bootloader's, and the
    (L)GPL texts that PySide6's wheels leave out. Returns the number of files copied."""
    copied: list[Path] = []
    sources = [(d.metadata["Name"].lower(), d) for d in runtime_distributions()]
    sources.append(("pyinstaller", importlib.metadata.distribution("pyinstaller")))
    for name, dist in sources:
        for inner, file in _license_files(dist):
            copied.append(dest / name / inner)
            copied[-1].parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file.locate(), copied[-1])
    for source, target in [
        (Path(sys.base_prefix) / "LICENSE.txt", dest / "python" / "LICENSE.txt"),
        *[(text, dest / "pyside6" / text.name) for text in sorted((ROOT / "packaging" / "licenses").glob("*.txt"))],
    ]:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append(target)
    return len(copied)


def build(out: Path) -> Path:
    dist, work = out / "dist", out / "work"
    subprocess.run(
        [
            sys.executable, "-m", "PyInstaller", str(ROOT / "packaging" / "snapocr.spec"),
            "--noconfirm", "--clean", "--distpath", str(dist), "--workpath", str(work),
        ],
        check=True,
    )
    app = dist / "snapocr"
    for extra in EXTRA_FILES:
        shutil.copy2(extra, app / extra.name)
    print(f"{copy_licenses(app / 'licenses')} license files")

    archive = out / f"snapocr-{version()}-windows-x64.zip"
    archive.unlink(missing_ok=True)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(app.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(dist).as_posix())
    return archive


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True, help="output folder (not inside the repository)")
    archive = build(parser.parse_args().out.resolve())
    print(f"{archive.stat().st_size / 2**20:.0f} MB")
    print(archive)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
