"""Cache de bibliotecas Verilator, aislada de ice-build."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .compiler import BuildRequest, VerilatorCompiler
from .ice_project import IcestudioProject
from .profile import BoardProfile

_CACHE_FORMAT = 1


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
    """Cache direccionada por contenido; nunca escribe dentro de ``ice-build``."""

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
        }, sort_keys=True).encode())
        for source in project.sources:
            digest.update(str(source.name).encode() + b"\0")
            digest.update(source.read_bytes())
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
        self, project: IcestudioProject, profile: BoardProfile, *, top_module: str = "top", verilator: str = "verilator"
    ) -> CachedBuild:
        fingerprint = self.fingerprint(project, profile, top_module, verilator)
        if cached := self.lookup(fingerprint, top_module):
            return cached

        self.root.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f"{fingerprint[:12]}-", dir=self.root))
        try:
            request = BuildRequest(project.main_v, profile, top_module, staging, verilator)
            library = VerilatorCompiler().build(request)
            final = self.root / fingerprint
            if final.exists():
                # Otra instancia pudo terminar el mismo build mientras ésta compilaba.
                cached = self.lookup(fingerprint, top_module)
                if cached:
                    return cached
                raise RuntimeError(f"Cache incompleta: {final}")
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
            # El staging queda disponible para diagnóstico sólo si ya fue promovido.
            if staging.exists():
                import shutil
                shutil.rmtree(staging, ignore_errors=True)
            raise

    @staticmethod
    def _library_name(top_module: str) -> str:
        from .compiler import shared_library_name
        return shared_library_name(f"V{top_module}_shared")
