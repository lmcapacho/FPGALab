"""Install local declarative packages without executing their contents."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from dataclasses import dataclass
import json
import re
import shutil
import stat
import tempfile
import zipfile
from typing import Callable

from .catalog import catalog_root, load_catalog, user_catalog_root
from .validate import validate_package


MAX_FILES = 100
MAX_BYTES = 20 * 1024 * 1024


@dataclass(frozen=True)
class InstallResult:
    identifier: str
    action: str  # installed, updated, unchanged, or cancelled


def _version_parts(version: str) -> tuple[tuple[int, int, int], tuple[str, ...]]:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?", version)
    if match is None:
        raise ValueError(f"Invalid installed package version: {version!r}")
    return tuple(int(match.group(index)) for index in (1, 2, 3)), tuple((match.group(4) or "").split(".")) if match.group(4) else ()


def _compare_versions(new: str, old: str) -> int:
    new_core, new_pre = _version_parts(new)
    old_core, old_pre = _version_parts(old)
    if new_core != old_core:
        return (new_core > old_core) - (new_core < old_core)
    if not new_pre or not old_pre:
        return (not new_pre) - (not old_pre)
    for left, right in zip(new_pre, old_pre):
        if left == right:
            continue
        if left.isdigit() and right.isdigit():
            return (int(left) > int(right)) - (int(left) < int(right))
        if left.isdigit() != right.isdigit():
            return -1 if left.isdigit() else 1
        return (left > right) - (left < right)
    return (len(new_pre) > len(old_pre)) - (len(new_pre) < len(old_pre))


def _same_files(left: Path, right: Path) -> bool:
    left_files = {path.relative_to(left): path for path in left.rglob("*") if path.is_file()}
    right_files = {path.relative_to(right): path for path in right.rglob("*") if path.is_file()}
    return left_files.keys() == right_files.keys() and all(
        left_files[name].read_bytes() == right_files[name].read_bytes() for name in left_files
    )


def _installed_version(target: Path) -> str | None:
    try:
        raw = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
        version = raw.get("package", {}).get("version")
        return version if isinstance(version, str) else None
    except (OSError, UnicodeError, ValueError, AttributeError) as exc:
        raise ValueError(f"Cannot read installed package {target.name!r}: {exc}") from exc


def _place_package(package: Path, target: Path) -> None:
    """Copy onto the destination filesystem, then replace with rollback."""
    work = Path(tempfile.mkdtemp(prefix=".fpgalab-update-", dir=target.parent))
    candidate = work / "candidate"
    backup = work / "backup"
    try:
        shutil.copytree(package, candidate)
        if target.exists():
            target.rename(backup)
        try:
            candidate.rename(target)
        except OSError:
            if backup.exists():
                backup.rename(target)
            raise
    finally:
        # If rollback itself failed, retain the backup for manual recovery.
        if not backup.exists() or target.exists():
            shutil.rmtree(work)


def _copy_folder(source: Path, destination: Path) -> None:
    files = [path for path in source.rglob("*") if path.is_file() or path.is_symlink()]
    if len(files) > MAX_FILES or any(path.is_symlink() for path in files):
        raise ValueError("Package has too many files or contains symbolic links")
    if sum(path.stat().st_size for path in files) > MAX_BYTES:
        raise ValueError("Package exceeds the 20 MB size limit")
    for path in files:
        relative = path.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)


def _extract_zip(source: Path, destination: Path) -> Path:
    try:
        archive = zipfile.ZipFile(source)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError(f"Cannot open ZIP: {exc}") from exc
    with archive:
        entries = [info for info in archive.infolist() if not info.is_dir()]
        if len(entries) > MAX_FILES or sum(info.file_size for info in entries) > MAX_BYTES:
            raise ValueError("ZIP exceeds the file count or 20 MB size limit")
        names = [PurePosixPath(info.filename) for info in entries]
        if any(name.is_absolute() or ".." in name.parts or "\\" in str(name) for name in names):
            raise ValueError("ZIP contains an unsafe path")
        if any(stat.S_ISLNK(info.external_attr >> 16) for info in entries):
            raise ValueError("ZIP contains symbolic links")
        roots = {name.parts[0] for name in names if name.parts}
        if len(roots) != 1 or not any(len(name.parts) == 2 and name.name == "manifest.json" for name in names):
            raise ValueError("ZIP must contain one package folder with manifest.json at its root")
        for info, name in zip(entries, names):
            target = destination.joinpath(*name.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as readable, target.open("wb") as writable:
                shutil.copyfileobj(readable, writable)
        return destination / next(iter(roots))


def install_package(
    source: Path, *, destination_root: Path | None = None,
    confirm_update: Callable[[str, str | None, str], bool] | None = None,
) -> InstallResult:
    """Validate a folder/ZIP, then install or confirm a newer version."""
    source = Path(source)
    destination_root = destination_root or user_catalog_root()
    if not source.is_dir() and not (source.is_file() and source.suffix.lower() == ".zip"):
        raise ValueError("Choose a peripheral folder or ZIP file")
    with tempfile.TemporaryDirectory(prefix="fpgalab-peripheral-") as temp:
        staging = Path(temp)
        package = _extract_zip(source, staging) if source.is_file() else staging / source.name
        if source.is_dir():
            _copy_folder(source, package)
        spec, issues = validate_package(package)
        if issues:
            raise ValueError("\n".join(issues))
        assert spec is not None
        if (catalog_root() / spec.id).exists():
            raise ValueError(f"Bundled peripheral {spec.id!r} cannot be replaced")
        destination_root.mkdir(parents=True, exist_ok=True)
        target = destination_root / spec.id
        action = "installed"
        if target.exists() or target.is_symlink():
            if target.is_symlink() or not target.is_dir():
                raise ValueError(f"Installed peripheral {spec.id!r} is not a regular package folder")
            if any(path.is_symlink() for path in target.rglob("*")):
                raise ValueError(f"Installed peripheral {spec.id!r} contains symbolic links")
            if _same_files(package, target):
                return InstallResult(spec.id, "unchanged")
            old_version = _installed_version(target)
            new_version = spec.package.version if spec.package else None
            if new_version is None:
                raise ValueError(f"Updating {spec.id!r} requires package.version in the new manifest")
            if old_version is not None and _compare_versions(new_version, old_version) <= 0:
                raise ValueError(f"{spec.id!r} needs a newer package version than {old_version} to update")
            if confirm_update is None:
                raise ValueError(f"Updating {spec.id!r} requires confirmation")
            if not confirm_update(spec.id, old_version, new_version):
                return InstallResult(spec.id, "cancelled")
            action = "updated"
        _place_package(package, target)
    load_catalog.cache_clear()
    return InstallResult(spec.id, action)


def uninstall_package(identifier: str, *, destination_root: Path | None = None) -> None:
    """Remove exactly one user-installed package, never a bundled package."""
    destination_root = destination_root or user_catalog_root()
    if not identifier or Path(identifier).name != identifier or identifier in {".", ".."}:
        raise ValueError("Invalid peripheral id")
    target = destination_root / identifier
    if target.is_symlink() or not target.is_dir() or not (target / "manifest.json").is_file():
        raise ValueError(f"User-installed peripheral {identifier!r} was not found")
    shutil.rmtree(target)
    load_catalog.cache_clear()
