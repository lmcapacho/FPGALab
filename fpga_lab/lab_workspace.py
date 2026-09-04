"""Visible, reusable workspace for FPGALab laboratory configurations."""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QSettings


@dataclass(frozen=True)
class LabDescriptor:
    """One reusable laboratory configuration stored in the global workspace."""

    name: str
    path: Path


def default_workspace_root() -> Path:
    """Return an Arduino-style visible workspace, with an environment override."""
    configured = os.environ.get("FPGALAB_WORKSPACE")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / (Path("Documents") / "FPGALab" if sys.platform == "win32" else "FPGALab")


class LabWorkspace:
    """Manage named lab files independently from Icestudio project locations."""

    LAST_SELECTED_KEY = "labs/last_selected_file"

    def __init__(self, root: str | Path | None = None, settings: QSettings | None = None):
        self.root = Path(root) if root else default_workspace_root()
        self.labs_dir = self.root / "labs"
        self._settings = settings or QSettings("FPGALab", "FPGALab")

    def ensure_default(self) -> Path:
        """Ensure the visible workspace and a starter lab exist."""
        self.labs_dir.mkdir(parents=True, exist_ok=True)
        default = self.labs_dir / "my-first-lab.lab.json"
        if not default.exists():
            self._write_lab(default, "My first lab")
        return default

    def labs(self) -> list[LabDescriptor]:
        self.ensure_default()
        result = []
        for path in sorted(self.labs_dir.glob("*.lab.json")):
            result.append(LabDescriptor(self._display_name(path), path))
        return result

    def last_selected(self) -> Path:
        """Return the most recently selected existing laboratory in this workspace."""
        default = self.ensure_default()
        stored = self._settings.value(self.LAST_SELECTED_KEY, "", type=str)
        candidate = Path(stored) if stored else None
        available = {descriptor.path.resolve() for descriptor in self.labs()}
        return candidate.resolve() if candidate is not None and candidate.resolve() in available else default

    def remember_selected(self, lab: str | Path) -> None:
        """Persist the selected reusable lab as a user preference."""
        target = Path(lab).resolve()
        if target not in {descriptor.path.resolve() for descriptor in self.labs()}:
            return
        self._settings.setValue(self.LAST_SELECTED_KEY, str(target))
        self._settings.sync()

    def delete(self, lab: str | Path) -> bool:
        """Delete one user-created lab without allowing the built-in starter lab to vanish."""
        target = Path(lab).resolve()
        if target.name == "my-first-lab.lab.json" or target.parent != self.labs_dir.resolve():
            return False
        if not target.is_file():
            return False
        target.unlink()
        stored = self._settings.value(self.LAST_SELECTED_KEY, "", type=str)
        if stored and Path(stored).resolve() == target:
            self._settings.remove(self.LAST_SELECTED_KEY)
            self._settings.sync()
        return True

    def create(self, name: str) -> LabDescriptor:
        """Create a named empty lab without overwriting existing configurations."""
        self.ensure_default()
        cleaned_name = name.strip() or "New Lab"
        candidate = self._available_path(cleaned_name)
        self._write_lab(candidate, cleaned_name)
        return LabDescriptor(cleaned_name, candidate)

    def duplicate(self, lab: str | Path) -> LabDescriptor:
        """Copy a user-visible lab configuration under a distinct name."""
        source = self._existing_lab_path(lab)
        raw = json.loads(source.read_text(encoding="utf-8"))
        original_name = (
            "My First Lab"
            if source.name == "my-first-lab.lab.json"
            else str(raw.get("metadata", {}).get("name") or source.stem.removesuffix(".lab"))
        )
        name = f"{self.base_name(original_name)} Copy"
        target = self._available_path(name)
        raw.setdefault("metadata", {})["name"] = name
        target.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
        return LabDescriptor(name, target)

    def rename(self, lab: str | Path, name: str) -> LabDescriptor:
        """Rename one user-created lab while preserving its configuration content."""
        source = self._existing_lab_path(lab)
        if source.name == "my-first-lab.lab.json":
            raise ValueError("The starter Lab cannot be renamed.")
        cleaned_name = name.strip()
        if not cleaned_name:
            raise ValueError("Lab name cannot be empty.")
        raw = json.loads(source.read_text(encoding="utf-8"))
        target = self._available_path(cleaned_name, exclude=source)
        raw.setdefault("metadata", {})["name"] = cleaned_name
        target.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
        if target != source:
            source.unlink()
        stored = self._settings.value(self.LAST_SELECTED_KEY, "", type=str)
        if stored and Path(stored).resolve() == source:
            self._settings.setValue(self.LAST_SELECTED_KEY, str(target.resolve()))
            self._settings.sync()
        return LabDescriptor(cleaned_name, target)

    def _available_path(self, name: str, exclude: Path | None = None) -> Path:
        stem = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "lab"
        candidate = self.labs_dir / f"{stem}.lab.json"
        suffix = 2
        while candidate.exists() and candidate.resolve() != (exclude.resolve() if exclude else None):
            candidate = self.labs_dir / f"{stem}-{suffix}.lab.json"
            suffix += 1
        return candidate

    def _existing_lab_path(self, lab: str | Path) -> Path:
        target = Path(lab).resolve()
        if target.parent != self.labs_dir.resolve() or not target.is_file():
            raise ValueError("Lab does not exist in this workspace.")
        return target

    @staticmethod
    def base_name(name: str) -> str:
        """Return a Lab name without a redundant trailing Lab suffix."""
        return name[:-4].rstrip() if name.casefold().endswith(" lab") else name

    @staticmethod
    def _display_name(path: Path) -> str:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return str(raw.get("metadata", {}).get("name") or path.name.removesuffix(".lab.json"))
        except (OSError, json.JSONDecodeError):
            return path.name.removesuffix(".lab.json")

    @staticmethod
    def _write_lab(path: Path, name: str) -> None:
        raw = {"metadata": {"name": name, "board_id": "alhambra-ii"}, "peripherals": []}
        path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
