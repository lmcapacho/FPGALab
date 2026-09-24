"""Preflight validation for shareable declarative peripheral folders."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

from fpga_lab import __version__
from .manifest import PeripheralSpec, parse_manifest


def _version_key(value: str) -> tuple[int, int, int, int, int]:
    import re

    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:(a|b|rc)(\d+))?", value)
    if match is None:
        raise ValueError(f"Invalid FPGALab version: {value}")
    major, minor, patch, phase, number = match.groups()
    return int(major), int(minor), int(patch), {"a": 0, "b": 1, "rc": 2, None: 3}[phase], int(number or 0)


def validate_package(directory: Path, *, current_version: str = __version__) -> tuple[PeripheralSpec | None, list[str]]:
    """Check one package without importing user code or modifying the catalog."""
    directory = Path(directory)
    issues: list[str] = []
    manifest = directory / "manifest.json"
    if not manifest.is_file():
        return None, [f"Missing manifest.json in {directory}"]
    try:
        raw = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, [f"Cannot read {manifest}: {exc}"]
    if not isinstance(raw, dict):
        return None, [f"{manifest}: root must be a JSON object"]
    try:
        spec = parse_manifest(raw, source=str(manifest), resource_root=directory)
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        return None, [str(exc)]
    if directory.name != spec.id:
        issues.append(f"Directory name {directory.name!r} must match peripheral id {spec.id!r}")

    from .renderers import renderer_for

    try:
        renderer_for(spec.visual["renderer"], spec.visual, directory)
    except (ValueError, TypeError, KeyError) as exc:
        issues.append(f"Unsupported renderer: {exc}")
    resources = []
    if spec.icon:
        resources.append(spec.icon)
    if spec.visual["renderer"] == "state_svg":
        resources.extend(spec.visual["states"].values())
    if spec.visual["renderer"] == "measured_svg":
        resources.extend((spec.visual["base_svg"], spec.visual["moving_svg"]))
    for resource in dict.fromkeys(resources):
        path = (directory / resource).resolve()
        if not path.is_relative_to(directory.resolve()) or path.suffix.lower() != ".svg":
            issues.append(f"Resource must be an SVG inside the package: {resource}")
            continue
        if not path.is_file():
            issues.append(f"Missing SVG resource: {resource}")
            continue
        try:
            root = ET.parse(path).getroot()
            if root.tag != "{http://www.w3.org/2000/svg}svg":
                issues.append(f"Not an SVG document: {resource}")
        except (OSError, ET.ParseError) as exc:
            issues.append(f"Invalid SVG {resource}: {exc}")
    if spec.package and _version_key(spec.package.minimum_fpgalab) > _version_key(current_version):
        issues.append(
            f"Requires FPGALab {spec.package.minimum_fpgalab} or newer; current version is {current_version}"
        )
    return spec, issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate one or more FPGALab peripheral packages")
    parser.add_argument("packages", nargs="+", type=Path, help="package folders containing manifest.json")
    args = parser.parse_args(argv)
    failed = False
    for directory in args.packages:
        spec, issues = validate_package(directory)
        if issues:
            failed = True
            print(f"FAIL {directory}")
            for issue in issues:
                print(f"  - {issue}")
        else:
            print(f"OK {directory}: {spec.id}")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
