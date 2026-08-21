"""Discover a usable Verilator installation for FPGALab."""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from .i18n import t


class ToolchainNotFoundError(FileNotFoundError):
    """Raised when FPGALab cannot find a usable Verilator executable."""


@dataclass(frozen=True)
class VerilatorToolchain:
    """One resolved Verilator executable and the environment it needs."""

    executable: Path
    source: str
    suite_root: Path | None = None

    def environment(self) -> dict[str, str]:
        """Return a process environment suitable for the selected toolchain."""
        environment = os.environ.copy()
        if self.suite_root is None:
            return environment
        binary_directory = self.suite_root / "bin"
        if binary_directory.is_dir():
            environment["PATH"] = str(binary_directory) + os.pathsep + environment.get("PATH", "")
        verilator_root = self.suite_root / "share" / "verilator"
        if verilator_root.is_dir():
            environment.setdefault("VERILATOR_ROOT", str(verilator_root))
        environment.setdefault("YOSYSHQ_ROOT", str(self.suite_root))
        return environment


def resolve_verilator(explicit: str | Path | None = None) -> VerilatorToolchain:
    """Resolve Verilator in priority order: Apio, OSS CAD Suite, then system PATH."""
    configured = explicit or os.environ.get("FPGALAB_VERILATOR")
    if configured:
        toolchain = _from_executable(Path(configured), "explicit configuration")
        if toolchain is not None:
            return toolchain
        raise ToolchainNotFoundError(
            t("Configured Verilator executable was not found: {path}", "No se encontró el ejecutable Verilator configurado: {path}", path=configured)
        )

    for root in _apio_suite_roots():
        if toolchain := _from_suite(root, "Apio/Icestudio"):
            return toolchain
    for root in _oss_cad_suite_roots():
        if toolchain := _from_suite(root, "OSS CAD Suite"):
            return toolchain
    if executable := shutil.which("verilator"):
        return VerilatorToolchain(Path(executable), "system PATH")

    raise ToolchainNotFoundError(t(
        "Verilator was not found. Install Icestudio/Apio, configure FPGALAB_OSS_CAD_SUITE, or install Verilator on PATH.",
        "No se encontró Verilator. Instale Icestudio/Apio, configure FPGALAB_OSS_CAD_SUITE o instale Verilator en PATH.",
    ))


def _apio_suite_roots() -> tuple[Path, ...]:
    """Return likely tool roots installed by Apio or exposed by Icestudio."""
    roots = [Path.home() / ".apio" / "packages" / "tools-oss-cad-suite"]
    for variable in ("ICESTUDIO_APIO", "APIO_HOME"):
        value = os.environ.get(variable)
        if not value:
            continue
        base = Path(value).expanduser()
        roots.extend((
            base,
            base / "tools-oss-cad-suite",
            base / "packages" / "tools-oss-cad-suite",
            base.parent / "tools-oss-cad-suite",
            base.parent / "packages" / "tools-oss-cad-suite",
        ))
    return _unique_paths(roots)


def _oss_cad_suite_roots() -> tuple[Path, ...]:
    """Return explicitly configured standalone OSS CAD Suite locations."""
    roots: list[Path] = []
    for variable in ("FPGALAB_OSS_CAD_SUITE", "OSS_CAD_SUITE"):
        value = os.environ.get(variable)
        if value:
            roots.append(Path(value).expanduser())
    return _unique_paths(roots)


def _from_suite(root: Path, source: str) -> VerilatorToolchain | None:
    """Find a suite executable, accepting either the suite or its parent directory."""
    for suite_root in (root, root / "oss-cad-suite"):
        for name in _executable_names():
            executable = suite_root / "bin" / name
            if executable.is_file():
                return VerilatorToolchain(executable, source, suite_root)
    return None


def _from_executable(path: Path, source: str) -> VerilatorToolchain | None:
    """Resolve an explicitly configured executable or command name."""
    candidate = path.expanduser()
    if candidate.is_file():
        return VerilatorToolchain(candidate.resolve(), source, _suite_parent(candidate))
    if found := shutil.which(str(candidate)):
        return VerilatorToolchain(Path(found), source)
    return None


def _suite_parent(executable: Path) -> Path | None:
    """Infer a suite root when the executable lives in a conventional bin directory."""
    return executable.parent.parent if executable.parent.name == "bin" else None


def _executable_names() -> tuple[str, ...]:
    """Return executable names for the host platform."""
    return ("verilator.exe", "verilator.bat", "verilator") if sys.platform == "win32" else ("verilator",)


def _unique_paths(paths: list[Path]) -> tuple[Path, ...]:
    """Keep candidate order while avoiding repeated filesystem probes."""
    result: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        normalized = path.expanduser()
        if normalized not in seen:
            result.append(normalized)
            seen.add(normalized)
    return tuple(result)
