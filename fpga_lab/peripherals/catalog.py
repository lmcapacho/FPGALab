"""Discover bundled and user-installed declarative peripherals."""

from __future__ import annotations

import json
import os
import sys
from functools import lru_cache
from pathlib import Path

from .manifest import PeripheralSpec, parse_manifest


def catalog_root() -> Path:
    return Path(__file__).resolve().parent


def user_catalog_root() -> Path:
    """Return the platform-native folder for no-code user peripherals."""
    override = os.environ.get("FPGALAB_PERIPHERALS_DIR")
    if override:
        return Path(override).expanduser()
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "FPGALab" / "peripherals"


def catalog_roots() -> tuple[Path, ...]:
    return catalog_root(), user_catalog_root()


def discover_catalog(roots: tuple[Path, ...]) -> dict[str, PeripheralSpec]:
    """Read deterministic directory-based manifests from the requested roots."""
    specs: dict[str, PeripheralSpec] = {}
    sources: dict[str, Path] = {}
    for root in roots:
        if not root.is_dir():
            continue
        for manifest in sorted(root.glob("*/manifest.json")):
            raw = json.loads(manifest.read_text(encoding="utf-8"))
            spec = parse_manifest(raw, source=str(manifest), resource_root=manifest.parent)
            if spec.id in specs:
                raise ValueError(
                    f"Duplicate peripheral id {spec.id!r}: {sources[spec.id]} and {manifest}"
                )
            if spec.id != manifest.parent.name:
                raise ValueError(f"{manifest}: directory name must match id {spec.id!r}")
            specs[spec.id] = spec
            sources[spec.id] = manifest
    return specs


@lru_cache(maxsize=1)
def load_catalog() -> dict[str, PeripheralSpec]:
    """Return the merged built-in and per-user catalog."""
    specs = discover_catalog(catalog_roots())
    if not specs:
        raise RuntimeError("FPGALab peripheral catalog is empty.")
    return specs


def spec_for(kind: str) -> PeripheralSpec:
    catalog = load_catalog()
    try:
        return catalog[kind]
    except KeyError as exc:
        raise ValueError(f"Unknown peripheral type: {kind}.") from exc


def icon_path_for(spec: PeripheralSpec) -> Path:
    """Resolve a plug-in icon, falling back to the bundled category artwork."""
    if spec.icon and spec.resource_root is not None:
        candidate = spec.resource_root / spec.icon
        if candidate.is_file():
            return candidate
    fallback = catalog_root().parent / "assets" / "icons" / "catalog" / f"{spec.category}.svg"
    if fallback.is_file():
        return fallback
    return catalog_root().parent / "assets" / "icons" / "catalog" / "other.svg"
