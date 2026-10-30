# PyInstaller spec of the portable builds (PRD F22-1, F24-1). Use packaging/build.py, which
# runs it and zips the result.
#
# onedir, not onefile: starts fast, and the Qt DLLs stay separate files that users can
# replace (LGPL). No UPX: compressed binaries trip antivirus heuristics.

import sys
import tomllib
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

ROOT = Path(SPECPATH).parent
MAC = sys.platform == "darwin"
# PyInstaller converts the PNG to .icns with Pillow.
ICON = ROOT / "src" / "snapocr" / "gui" / "assets" / ("snapocr-256.png" if MAC else "snapocr.ico")

datas = [
    # The PP-OCR models and rapidocr's YAML configs: OCR works offline from the bundle.
    *collect_data_files("rapidocr", excludes=["**/*.pyi", "**/py.typed"]),
    # Tray and window icon, loaded with importlib.resources.
    *collect_data_files("snapocr.gui", includes=["assets/*"]),
]

a = Analysis(
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(ROOT / "src")],
    datas=datas,
    # Loaded by name (launch.platform_kit). Both are listed; the other platform's stays unused.
    hiddenimports=["snapocr.gui.platform.win", "snapocr.gui.platform.mac.kit"],
    excludes=["tkinter", "pytest", "hypothesis", "IPython"],
    noarchive=False,
)
# Never loaded by snapocr: OpenCV's video I/O (no video is read) and Qt's software OpenGL
# (plain widgets, no OpenGL). About 50 MB.
UNUSED = ("opencv_videoio_ffmpeg", "opengl32sw.dll")
a.binaries = [b for b in a.binaries if not any(u in Path(b[0]).name for u in UNUSED)]

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="snapocr",
    console=False,
    icon=str(ICON),
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="snapocr", upx=False)

if MAC:
    VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    app = BUNDLE(
        coll,
        name="snapocr.app",
        icon=str(ICON),
        bundle_identifier="io.github.jeremy-creater.snapocr",
        version=VERSION,
        info_plist={"LSUIElement": True, "NSHighResolutionCapable": True},
    )
