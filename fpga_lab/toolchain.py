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


class ToolchainPrerequisiteError(RuntimeError):
    """Raised when Verilator is present but cannot build a native model."""


_DLL_DIRECTORIES: list[object] = []


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
        binary_directories = (
            self.suite_root / "bin",
            self.suite_root / "share" / "verilator" / "bin",
            *_msys2_binary_directories(),
        )
        available_directories = [str(directory) for directory in binary_directories if directory.is_dir()]
        if available_directories:
            environment["PATH"] = os.pathsep.join(available_directories + [environment.get("PATH", "")])
        verilator_root = self.suite_root / "share" / "verilator"
        if verilator_root.is_dir():
            environment.setdefault("VERILATOR_ROOT", str(verilator_root))
        environment.setdefault("YOSYSHQ_ROOT", str(self.suite_root))
        return environment

    def validate_build_prerequisites(self) -> None:
        """Ensure the native build tools required by Verilator are available."""
        environment = self.environment()
        missing = [command for command in ("make", "g++") if not _command_exists(command, environment)]
        if not missing:
            return
        if sys.platform == "win32":
            raise ToolchainPrerequisiteError(t(
                "Verilator was found, but Windows needs MSYS2 build tools: {tools}. Install MSYS2, then install make and a MinGW-w64 C++ compiler.",
                "Se encontró Verilator, pero Windows necesita las herramientas de compilación de MSYS2: {tools}. Instale MSYS2 y luego make y un compilador C++ MinGW-w64.",
                tools=", ".join(missing),
            ))
        raise ToolchainPrerequisiteError(t(
            "Verilator was found, but the required build tools are missing: {tools}.",
            "Se encontró Verilator, pero faltan las herramientas de compilación requeridas: {tools}.",
            tools=", ".join(missing),
        ))

    def activate_runtime(self) -> None:
        """Expose MinGW runtime DLL directories to the current Windows process."""
        if sys.platform != "win32" or not hasattr(os, "add_dll_directory"):
            return
        for directory in _msys2_binary_directories():
            if directory.is_dir():
                _DLL_DIRECTORIES.append(os.add_dll_directory(str(directory)))


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


def _msys2_binary_directories() -> tuple[Path, ...]:
    """Return standard MSYS2 directories when FPGALab runs on Windows."""
    if sys.platform != "win32":
        return ()
    root = Path(os.environ.get("MSYS2_ROOT", os.environ.get("SystemDrive", "C:") + "\\msys64"))
    return (root / "usr" / "bin", root / "ucrt64" / "bin", root / "mingw64" / "bin")


def _command_exists(command: str, environment: dict[str, str]) -> bool:
    """Check commands using the target platform's executable naming convention."""
    names = (f"{command}.exe", command) if sys.platform == "win32" else (command,)
    directories = [Path(item) for item in environment.get("PATH", "").split(os.pathsep) if item]
    return any((directory / name).is_file() for directory in directories for name in names)


def _apio_suite_roots() -> tuple[Path, ...]:
    """Return likely tool roots installed by Apio or exposed by Icestudio."""
    package_names = ("oss-cad-suite", "tools-oss-cad-suite")
    roots = [
        Path.home() / ".icestudio" / "apio" / "packages" / name
        for name in package_names
    ] + [
        Path.home() / ".apio" / "packages" / name
        for name in package_names
    ]
    for variable in ("ICESTUDIO_APIO", "APIO_HOME"):
        value = os.environ.get(variable)
        if not value:
            continue
        base = Path(value).expanduser()
        roots.append(base)
        for name in package_names:
            roots.extend((
                base / name,
                base / "packages" / name,
                base.parent / name,
                base.parent / "packages" / name,
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
    """Find a native suite executable, accepting either the suite or its parent directory."""
    for suite_root in (root, root / "oss-cad-suite"):
        for relative_path in _suite_executable_paths():
            executable = suite_root / relative_path
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


def _suite_executable_paths() -> tuple[Path, ...]:
    """Return native Verilator paths packaged by OSS CAD Suite."""
    if sys.platform == "win32":
        return (
            Path("share") / "verilator" / "bin" / "verilator_bin.exe",
            Path("bin") / "verilator_bin.exe",
            Path("bin") / "verilator.exe",
        )
    return (Path("bin") / "verilator", Path("share") / "verilator" / "bin" / "verilator")


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
