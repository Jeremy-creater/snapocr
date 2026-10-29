"""Build the Windows portable zip (PRD F22-1).

    python packaging/build.py --out D:\\DevLocal\\build\\snapocr

Runs PyInstaller with ``packaging/snapocr.spec`` (work files under ``<out>/work``), adds the
license files and ``README.txt`` next to ``snapocr.exe``, and writes
``<out>/snapocr-<version>-windows-x64.zip`` whose top level is the ``snapocr`` folder.
Prints the zip path on the last line.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTRA_FILES = [ROOT / "LICENSE", ROOT / "THIRD_PARTY_NOTICES.md", ROOT / "packaging" / "README.txt"]


def version() -> str:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


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
