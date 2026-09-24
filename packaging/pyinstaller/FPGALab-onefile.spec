# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files
from PyQt6.QtCore import QLibraryInfo


repository_root = Path(SPECPATH).parents[1]
datas = collect_data_files("fpga_lab")
datas += [(str(repository_root / name), ".") for name in ("LICENSE", "NOTICE", "AUTHORS.md", "AI_USAGE.md")]
qtbase_es = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)) / "qtbase_es.qm"
datas.append((str(qtbase_es), "fpga_lab/translations"))

a = Analysis(
    [str(Path(SPECPATH) / "launcher.py")],
    pathex=["."],
    binaries=[],
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
