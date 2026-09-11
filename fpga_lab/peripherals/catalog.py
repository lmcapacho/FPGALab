"""Discover bundled peripheral manifests next to this package."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .manifest import PeripheralSpec, parse_manifest


def catalog_root() -> Path:
    return Path(__file__).resolve().parent


@lru_cache(maxsize=1)
def load_catalog() -> dict[str, PeripheralSpec]:
    """Return catalog id → spec for every ``*/manifest.json`` under this package."""
    specs: dict[str, PeripheralSpec] = {}
    for manifest in sorted(catalog_root().glob("*/manifest.json")):
        raw = json.loads(manifest.read_text(encoding="utf-8"))
        spec = parse_manifest(raw, source=str(manifest))
        if spec.id in specs:
            raise ValueError(f"Duplicate peripheral id {spec.id!r}")
        if spec.id != manifest.parent.name:
            raise ValueError(f"{manifest}: directory name must match id {spec.id!r}")
        specs[spec.id] = spec
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
    if spec.icon:
        candidate = catalog_root() / spec.id / spec.icon
        if candidate.is_file():
            return candidate
    fallback = catalog_root().parent / "assets" / "icons" / "catalog" / f"{spec.category}.svg"
    if fallback.is_file():
        return fallback
    return catalog_root().parent / "assets" / "icons" / "catalog" / "other.svg"
