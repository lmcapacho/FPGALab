# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.depend.bindepend import resolve_library_path
from PyQt6.QtCore import QLibraryInfo

sys.path.insert(0, SPECPATH)
from linux_runtime import collect_linux_qt_runtime

repository_root = Path(SPECPATH).parents[1]
datas = collect_data_files("fpga_lab")
datas += [(str(repository_root / name), ".") for name in ("LICENSE", "NOTICE", "AUTHORS.md", "AI_USAGE.md")]
qt_translations = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath))
datas += [(str(path), "fpga_lab/translations") for path in sorted(qt_translations.glob("qtbase_*.qm"))]

a = Analysis(
    [str(Path(SPECPATH) / "launcher.py")],
    pathex=["."],
    binaries=collect_linux_qt_runtime(resolve_library_path),
    datas=datas,
    hiddenimports=["PyQt6.QtSvg", "PyQt6.QtSvgWidgets"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="FPGALab",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(repository_root / "fpga_lab" / "assets" / "icons" / "fpgalab.ico"),
)
