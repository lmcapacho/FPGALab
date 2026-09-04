"""Verilator library cache, isolated from ``ice-build``."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .compiler import BuildRequest, VerilatorCompiler
from .ice_project import IcestudioProject
from .i18n import t
from .profile import BoardProfile
from .toolchain import resolve_verilator

_CACHE_FORMAT = 3
_NATIVE_DIR = Path(__file__).resolve().parent / "native"


def default_cache_root() -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "fpgalab" / "verilator"


@dataclass(frozen=True)
class CachedBuild:
    fingerprint: str
    directory: Path
    library: Path
    reused: bool


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
        return CachedBuild(fingerprint, directory, library, True)

    def build_or_reuse(
        self, project: IcestudioProject, profile: BoardProfile, *, top_module: str = "top", verilator: str | None = None
    ) -> CachedBuild:
        toolchain = resolve_verilator(verilator)
        toolchain.activate_runtime()
        fingerprint = self.fingerprint(project, profile, top_module, str(toolchain.executable))
        if cached := self.lookup(fingerprint, top_module):
            return cached
        toolchain.validate_build_prerequisites()

        self.root.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f"{fingerprint[:12]}-", dir=self.root))
        try:
            request = BuildRequest(
                project.main_v,
                profile,
                top_module,
                staging,
                str(toolchain.executable),
                toolchain.environment(),
                toolchain.make_variables(),
            )
            library = VerilatorCompiler().build(request)
            final = self.root / fingerprint
            if final.exists():
                # Another instance may have completed this build while this one ran.
                cached = self.lookup(fingerprint, top_module)
                if cached:
                    return cached
                raise RuntimeError(t("Incomplete cache: {path}", path=final))
            manifest = {
                "format": _CACHE_FORMAT,
                "fingerprint": fingerprint,
                "ice_file": str(project.ice_file),
                "main_v": str(project.main_v),
                "pcf": str(project.pcf) if project.pcf else None,
                "top_module": top_module,
                "library": str(library.relative_to(staging)),
            }
            (staging / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            staging.rename(final)
            return CachedBuild(fingerprint, final, final / library.relative_to(staging), False)
        except Exception:
            # Keep staging only until it is promoted; clean failures for future retries.
            if staging.exists():
                import shutil
                shutil.rmtree(staging, ignore_errors=True)
            raise

    @staticmethod
    def _library_name(top_module: str) -> str:
        from .compiler import shared_library_name
        return shared_library_name(f"V{top_module}_shared")
