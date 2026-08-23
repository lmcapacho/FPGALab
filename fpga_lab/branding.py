"""Application identity and resource lookup shared by source and frozen builds."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtGui import QIcon


def asset_path(*parts: str) -> Path:
    """Return a packaged asset path in both normal and PyInstaller executions."""
    return Path(__file__).resolve().parent / "assets" / Path(*parts)


def application_icon() -> QIcon:
    """Return the FPGALab icon for application, window, dock, and taskbar usage."""
    for filename in ("fpgalab.png", "fpgalab.ico", "fpgalab.svg"):
        path = asset_path("icons", filename)
        if path.is_file():
            return QIcon(str(path))
    return QIcon()
