"""Install local declarative packages without executing their contents."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import zipfile

from .catalog import catalog_root, load_catalog, user_catalog_root
from .validate import validate_package


MAX_FILES = 100
MAX_BYTES = 20 * 1024 * 1024


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


def install_package(source: Path, *, destination_root: Path | None = None) -> str:
    """Validate a folder/ZIP then atomically add it to the user catalog.

    Existing packages are never overwritten; updates need a separate policy.
    """
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
        if (catalog_root() / spec.id).exists() or (destination_root / spec.id).exists():
            raise ValueError(f"Peripheral {spec.id!r} is already installed")
        destination_root.mkdir(parents=True, exist_ok=True)
        shutil.move(str(package), str(destination_root / spec.id))
    load_catalog.cache_clear()
    return spec.id


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
