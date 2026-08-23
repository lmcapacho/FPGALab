# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files


datas = collect_data_files("fpga_lab")

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
    [],
    exclude_binaries=True,
    name="FPGALab",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(Path(SPECPATH).parents[1] / "fpga_lab" / "assets" / "icons" / "fpgalab.ico"),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="FPGALab",
)
