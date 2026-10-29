# PyInstaller spec of the Windows portable build (PRD F22-1). Use packaging/build.py, which
# runs it and zips the result.
#
# onedir, not onefile: starts fast, and the Qt DLLs stay separate files that users can
# replace (LGPL). No UPX: compressed binaries trip antivirus heuristics.

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

ROOT = Path(SPECPATH).parent
ICON = ROOT / "src" / "snapocr" / "gui" / "assets" / "snapocr.ico"

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
