"""Visible, reusable workspace for FPGALab laboratory configurations."""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path


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

    def __init__(self, root: str | Path | None = None):
        self.root = Path(root) if root else default_workspace_root()
        self.labs_dir = self.root / "labs"

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

    def create(self, name: str) -> LabDescriptor:
        """Create a named empty lab without overwriting existing configurations."""
        self.ensure_default()
        cleaned_name = name.strip() or "New lab"
        stem = re.sub(r"[^a-z0-9]+", "-", cleaned_name.lower()).strip("-") or "lab"
        candidate = self.labs_dir / f"{stem}.lab.json"
        suffix = 2
        while candidate.exists():
            candidate = self.labs_dir / f"{stem}-{suffix}.lab.json"
            suffix += 1
        self._write_lab(candidate, cleaned_name)
        return LabDescriptor(cleaned_name, candidate)

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
