"""Verilator library cache, isolated from ``ice-build``."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from .compiler import BuildRequest, VerilatorCompiler, verilator_optimization_flags
from .ice_project import IcestudioProject
from .i18n import t
from .profile import BoardProfile
from .toolchain import resolve_verilator

_CACHE_FORMAT = 5
_NATIVE_DIR = Path(__file__).resolve().parent / "native"
_MIN_CACHE_BUDGET = 128 * 1024 * 1024
_MAX_CACHE_BUDGET = 512 * 1024 * 1024
_CACHE_DISK_FRACTION = 0.01
_CACHE_TARGET_FRACTION = 0.80
_EXACT_BUILDS_PER_PROJECT = 2
_WORKSPACES_PER_PROJECT = 2
_TEMP_MAX_AGE_SECONDS = 24 * 60 * 60
_WORKSPACE_MAX_AGE_SECONDS = 30 * 24 * 60 * 60
_LOW_DISK_THRESHOLD = 2 * 1024 * 1024 * 1024
_LOW_DISK_BUDGET = 64 * 1024 * 1024


def default_cache_root() -> Path:
    """Return a native per-user cache location, migrating the legacy path."""
    legacy = Path.home() / ".cache" / "fpgalab" / "verilator"
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        current = base / "FPGALab" / "Cache" / "verilator"
    elif sys.platform == "darwin":
        current = Path.home() / "Library" / "Caches" / "FPGALab" / "verilator"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
        current = base / "fpgalab" / "verilator"
    if current != legacy and legacy.is_dir() and not current.exists():
        try:
            current.parent.mkdir(parents=True, exist_ok=True)
            legacy.rename(current)
        except OSError:
            return legacy
    return current


@dataclass(frozen=True)
class CachedBuild:
    fingerprint: str
    directory: Path
    library: Path
    reused: bool
    compatibility_mode: bool = False
    incremental: bool = False


class VerilatorBuildCache:
    """Content-addressed cache that never writes inside ``ice-build``."""

    def __init__(self, root: str | Path | None = None):
        self.root = Path(root) if root else default_cache_root()

    def fingerprint(
        self, project: IcestudioProject, profile: BoardProfile, top_module: str, verilator: str
    ) -> str:
        digest = hashlib.sha256()
        digest.update(f"fpgalab-cache:{_CACHE_FORMAT}\0{top_module}\0{verilator}\0".encode())
        digest.update(json.dumps({
            "board_name": profile.board_name,
            "inputs": profile.inputs,
            "outputs": profile.outputs,
            "observed": profile.observed,
            "clock_name": profile.clock_name,
        }, sort_keys=True).encode())
        for source in project.sources:
            digest.update(str(source.name).encode() + b"\0")
            digest.update(source.read_bytes())
        if _NATIVE_DIR.is_dir():
            for path in sorted(p for p in _NATIVE_DIR.iterdir() if p.is_file()):
                digest.update(path.name.encode() + b"\0")
                digest.update(path.read_bytes())
        return digest.hexdigest()

    def incremental_key(
        self, project: IcestudioProject, top_module: str,
        verilator: str, verilator_flags: tuple[str, ...],
    ) -> str:
        """Identify a stable Make workspace without including changing HDL content."""
        digest = hashlib.sha256()
        digest.update(f"fpgalab-incremental:{_CACHE_FORMAT}\0{top_module}\0{verilator}\0".encode())
        digest.update(str(project.ice_file.resolve()).encode())
        digest.update(json.dumps({
            "verilator_flags": verilator_flags,
        }, sort_keys=True).encode())
        return digest.hexdigest()

    @staticmethod
    def project_key(project: IcestudioProject) -> str:
        """Return a stable, privacy-preserving identifier for cache retention."""
        return hashlib.sha256(str(project.ice_file.resolve()).encode()).hexdigest()

    def usage_bytes(self) -> int:
        """Return the complete managed cache size."""
        return _directory_size(self.root)

    def budget_bytes(self) -> int:
        """Use one percent of the disk, bounded to a responsible range."""
        anchor = self.root
        while not anchor.exists() and anchor != anchor.parent:
            anchor = anchor.parent
        disk = shutil.disk_usage(anchor)
        if disk.free < _LOW_DISK_THRESHOLD:
            return _LOW_DISK_BUDGET
        total = disk.total
        return max(_MIN_CACHE_BUDGET, min(_MAX_CACHE_BUDGET, int(total * _CACHE_DISK_FRACTION)))

    def maintain(
        self,
        *,
        protected_fingerprints: set[str] | None = None,
        protected_workspace: Path | None = None,
    ) -> None:
        """Silently enforce age, per-project, and global LRU retention limits."""
        if not self.root.is_dir():
            return
        protected = protected_fingerprints or set()
        now = time.time()
        for path in self.root.iterdir():
            if path.is_dir() and path.name.startswith(".") and now - path.stat().st_mtime > _TEMP_MAX_AGE_SECONDS:
                shutil.rmtree(path, ignore_errors=True)

        exact_entries = self._exact_entries()
        by_project: dict[str, list[tuple[float, Path]]] = {}
        for last_used, path, project_key in exact_entries:
            by_project.setdefault(project_key, []).append((last_used, path))
        for entries in by_project.values():
            entries.sort(reverse=True)
            for _last_used, path in entries[_EXACT_BUILDS_PER_PROJECT:]:
                if path.name not in protected:
                    shutil.rmtree(path, ignore_errors=True)

        workspace_entries = self._workspace_entries()
        workspaces_by_project: dict[str, list[tuple[float, Path]]] = {}
        for last_used, path, project_key in workspace_entries:
            workspaces_by_project.setdefault(project_key, []).append((last_used, path))
        for entries in workspaces_by_project.values():
            entries.sort(reverse=True)
            for _last_used, path in entries[_WORKSPACES_PER_PROJECT:]:
                if path != protected_workspace:
                    shutil.rmtree(path, ignore_errors=True)
        for last_used, path, _project_key in self._workspace_entries():
            if path != protected_workspace and now - last_used > _WORKSPACE_MAX_AGE_SECONDS:
                shutil.rmtree(path, ignore_errors=True)

        budget = self.budget_bytes()
        usage = self.usage_bytes()
        if usage <= budget:
            return
        target = int(budget * _CACHE_TARGET_FRACTION)
        candidates = [
            (last_used, path)
            for last_used, path, _project_key in self._exact_entries()
            if path.name not in protected
        ] + [
            (last_used, path)
            for last_used, path, _project_key in self._workspace_entries()
            if path != protected_workspace
        ]
        for _last_used, path in sorted(candidates):
            size = _directory_size(path)
            shutil.rmtree(path, ignore_errors=True)
            usage -= size
            if usage <= target:
                break

    def _exact_entries(self) -> list[tuple[float, Path, str]]:
        entries = []
        for path in self.root.iterdir() if self.root.is_dir() else ():
            manifest_path = path / "manifest.json"
            if not path.is_dir() or path.name.startswith(".") or path.name == "_incremental" or not manifest_path.is_file():
                continue
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            project_key = str(data.get("project_key") or data.get("ice_file") or path.name)
            entries.append((float(data.get("last_used", path.stat().st_mtime)), path, project_key))
        return entries

    def _workspace_entries(self) -> list[tuple[float, Path, str]]:
        root = self.root / "_incremental"
        entries = []
        for path in root.iterdir() if root.is_dir() else ():
            if not path.is_dir():
                continue
            metadata_path = path / "workspace.json"
            try:
                data = json.loads(metadata_path.read_text(encoding="utf-8"))
                last_used = float(data.get("last_used", path.stat().st_mtime))
                project_key = str(data.get("project_key") or path.name)
            except (OSError, ValueError, json.JSONDecodeError):
                last_used = path.stat().st_mtime
                project_key = path.name
            entries.append((last_used, path, project_key))
        return entries

    def lookup(self, fingerprint: str, top_module: str = "top") -> CachedBuild | None:
        directory = self.root / fingerprint
        manifest = directory / "manifest.json"
        library = directory / "obj_dir" / self._library_name(top_module)
        if not manifest.is_file() or not library.is_file():
            return None
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        if data.get("fingerprint") != fingerprint or data.get("format") != _CACHE_FORMAT:
            return None
        data["last_used"] = time.time()
        manifest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return CachedBuild(fingerprint, directory, library, True, bool(data.get("compatibility_mode", False)))

    def build_or_reuse(
        self, project: IcestudioProject, profile: BoardProfile, *, top_module: str = "top",
        verilator: str | None = None, optimization_mode: str = "automatic",
    ) -> CachedBuild:
        toolchain = resolve_verilator(verilator)
        toolchain.activate_runtime()
        compatibility_flags = verilator_optimization_flags(project.main_v, optimization_mode)
        project_key = self.project_key(project)
        fingerprint = self.fingerprint(project, profile, top_module, str(toolchain.executable))
        if compatibility_flags:
            fingerprint = hashlib.sha256(
                f"{fingerprint}\0{' '.join(compatibility_flags)}".encode()
            ).hexdigest()
        if cached := self.lookup(fingerprint, top_module):
            return cached
        toolchain.validate_build_prerequisites()

        self.root.mkdir(parents=True, exist_ok=True)
        workspace = self.root / "_incremental" / self.incremental_key(
            project, top_module, str(toolchain.executable), compatibility_flags,
        )
        makefile = workspace / "obj_dir" / f"V{top_module}.mk"
        incremental = makefile.is_file()
        workspace.mkdir(parents=True, exist_ok=True)
        publish = Path(tempfile.mkdtemp(prefix=f".{fingerprint[:12]}-", dir=self.root))
        try:
            request = BuildRequest(
                project.main_v,
                profile,
                top_module,
                workspace,
                str(toolchain.executable),
                toolchain.environment(),
                toolchain.make_variables(),
                compatibility_flags,
            )
            library = VerilatorCompiler().build(request)
            final = self.root / fingerprint
            if final.exists():
                # Another instance may have completed this build while this one ran.
                cached = self.lookup(fingerprint, top_module)
                if cached:
                    shutil.rmtree(publish, ignore_errors=True)
                    return cached
                raise RuntimeError(t("Incomplete cache: {path}", path=final))
            manifest = {
                "format": _CACHE_FORMAT,
                "fingerprint": fingerprint,
                "ice_file": str(project.ice_file),
                "main_v": str(project.main_v),
                "pcf": str(project.pcf) if project.pcf else None,
                "top_module": top_module,
                "library": str(Path("obj_dir") / library.name),
                "compatibility_mode": bool(compatibility_flags),
                "incremental": incremental,
                "project_key": project_key,
                "last_used": time.time(),
            }
            published_library = publish / "obj_dir" / library.name
            published_library.parent.mkdir(parents=True)
            shutil.copy2(library, published_library)
            (publish / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            publish.rename(final)
            (workspace / "workspace.json").write_text(json.dumps({
                "project_key": project_key,
                "last_used": time.time(),
            }, indent=2) + "\n", encoding="utf-8")
            result = CachedBuild(
                fingerprint,
                final,
                final / "obj_dir" / library.name,
                False,
                bool(compatibility_flags),
                incremental,
            )
            self.maintain(protected_fingerprints={fingerprint}, protected_workspace=workspace)
            return result
        except Exception:
            # Keep the incremental workspace: Make can reuse valid objects on retry.
            if publish.exists():
                shutil.rmtree(publish, ignore_errors=True)
            raise

    @staticmethod
    def _library_name(top_module: str) -> str:
        from .compiler import shared_library_name
        return shared_library_name(f"V{top_module}_shared")


def _directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    total = 0
    for entry in path.rglob("*"):
        if entry.is_file():
            try:
                total += entry.stat().st_size
            except OSError:
                pass
    return total
