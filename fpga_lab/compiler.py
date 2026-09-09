"""Reproducible asynchronous compilation from Verilog to a shared library."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .cpp_wrapper import render_cpp_wrapper
from .profile import BoardProfile


class VerilatorBuildError(RuntimeError):
    """Verilator failure including its captured diagnostic output."""


_CONTINUOUS_ASSIGNMENT = re.compile(
    r"^\s*assign\s+([A-Za-z_$][A-Za-z0-9_$]*(?:\s*\[[^\]]+\])?)\s*=",
    re.MULTILINE,
)


def verilator_compatibility_flags(verilog: Path) -> tuple[str, ...]:
    """Avoid a Verilator DFG pathological case caused by repeated net drivers.

    Some Icestudio label fan-outs are emitted as several equivalent continuous
    assignments to the same net. Verilator 5.047 can spend an unbounded amount
    of time optimizing that graph, while disabling only DFG handles it quickly.
    """
    source = verilog.read_text(encoding="utf-8", errors="replace")
    targets: set[str] = set()
    for match in _CONTINUOUS_ASSIGNMENT.finditer(source):
        target = re.sub(r"\s+", "", match.group(1))
        if target in targets:
            return ("-fno-dfg",)
        targets.add(target)
    return ()


def verilator_optimization_flags(verilog: Path, mode: str) -> tuple[str, ...]:
    """Resolve a user-facing optimization mode to Verilator arguments."""
    normalized = mode.casefold()
    if normalized == "compatibility":
        return ("-fno-dfg",)
    if normalized == "standard":
        return ()
    if normalized == "automatic":
        return verilator_compatibility_flags(verilog)
    raise ValueError(f"Unknown Verilator optimization mode: {mode}")


def shared_library_name(stem: str = "Vtop_shared") -> str:
    if sys.platform == "win32":
        return f"{stem}.dll"
    if sys.platform == "darwin":
        return f"lib{stem}.dylib"
    return f"lib{stem}.so"


def shared_library_linker_flag() -> str:
    """Return the platform linker option for a loadable native model."""
    return "-dynamiclib" if sys.platform == "darwin" else "-shared"


@dataclass(frozen=True)
class BuildRequest:
    verilog: Path
    profile: BoardProfile
    top_module: str = "top"
    build_dir: Path = Path("build/verilator")
    verilator: str = "verilator"
    environment: dict[str, str] | None = None
    make_variables: tuple[str, ...] = ()
    verilator_flags: tuple[str, ...] = ()


class VerilatorCompiler:
    """Build a .so/.dll without a shell; suitable for QProcess execution."""

    def prepare(self, request: BuildRequest) -> tuple[Path, list[str]]:
        verilog = request.verilog.resolve()
        if not verilog.is_file():
            raise FileNotFoundError(verilog)
        if not shutil.which(request.verilator) and not Path(request.verilator).is_file():
            raise FileNotFoundError(f"Verilator was not found: {request.verilator}")

        build_dir = request.build_dir.resolve()
        obj_dir = build_dir / "obj_dir"
        obj_dir.mkdir(parents=True, exist_ok=True)
        wrapper = build_dir / "sim_main.cpp"
        _write_if_changed(wrapper, render_cpp_wrapper(request.profile, f"V{request.top_module}"))
        native = Path(__file__).resolve().parent / "native"
        streaming = native / "sim_streaming.cpp"
        decoder = native / "vga_decoder.cpp"

        library = shared_library_name(f"V{request.top_module}_shared")
        cxx_flags = f"-O3 -DNDEBUG -fPIC -march=native -DVL_TIME_CONTEXT -I{native}"
        linker_flags = shared_library_linker_flag()
        # --exe writes a Makefile.  Building it in a separate process is
        # important on Windows: Verilator is native while Make runs in MSYS2.
        args = [
            "--cc", str(verilog), "--top-module", request.top_module, "--prefix", f"V{request.top_module}",
            "--Mdir", str(obj_dir), "-O3", "-Wno-fatal",
            *request.verilator_flags,
            "--exe", str(wrapper), str(streaming), str(decoder),
            # The wrapper owns a VerilatedContext.  VL_TIME_CONTEXT prevents
            # MinGW from requiring the legacy sc_time_stamp() callback.
            "-CFLAGS", cxx_flags,
            "-LDFLAGS", linker_flags, "-o", library,
        ]
        return obj_dir / library, args

    def build(self, request: BuildRequest) -> Path:
        target, args = self.prepare(request)
        generated_state = _generated_file_state(target.parent, f"V{request.top_module}")
        self._run(
            [request.verilator, *args],
            cwd=request.build_dir.resolve(),
            environment=request.environment,
        )
        _restore_unchanged_timestamps(generated_state)
        make = shutil.which("make", path=(request.environment or os.environ).get("PATH"))
        if make is None:
            raise RuntimeError("Verilator generated its Makefile but GNU Make was not found.")
        self._run(
            [make, "-C", str(target.parent), "-f", f"V{request.top_module}.mk", "-j", "OPT_FAST=-O3", *request.make_variables],
            cwd=request.build_dir.resolve(),
            environment=request.environment,
        )
        if not target.exists():
            raise RuntimeError(f"Verilator completed but did not produce {target}")
        return target

    @staticmethod
    def _run(command: list[str], *, cwd: Path, environment: dict[str, str] | None) -> None:
        """Run one build phase and retain Verilator diagnostics on failure."""
        completed = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=environment,
            creationflags=_subprocess_creation_flags(),
        )
        if completed.returncode:
            output = completed.stdout.strip() or "Verilator did not provide diagnostic output."
            raise VerilatorBuildError(output)


def _subprocess_creation_flags() -> int:
    """Keep native build tools hidden behind the FPGALab progress UI on Windows."""
    if sys.platform == "win32":
        return int(getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))
    return 0


def _write_if_changed(path: Path, content: str) -> None:
    """Preserve timestamps so Make can reuse an unchanged generated wrapper."""
    try:
        if path.read_text(encoding="utf-8") == content:
            return
    except FileNotFoundError:
        pass
    path.write_text(content, encoding="utf-8")


def _generated_file_state(directory: Path, prefix: str) -> dict[Path, tuple[bytes, int, int]]:
    """Capture hashes and timestamps of generated sources used by Make."""
    binary_suffixes = {".o", ".a", ".so", ".dll", ".dylib"}
    state: dict[Path, tuple[bytes, int, int]] = {}
    for path in directory.glob(f"{prefix}*"):
        if not path.is_file() or path.suffix in binary_suffixes:
            continue
        metadata = path.stat()
        state[path] = (_file_digest(path), metadata.st_atime_ns, metadata.st_mtime_ns)
    return state


def _restore_unchanged_timestamps(state: dict[Path, tuple[bytes, int, int]]) -> None:
    """Undo timestamp-only Verilator rewrites so Make sees unchanged sources."""
    for path, (digest, access_time, modification_time) in state.items():
        if path.is_file() and _file_digest(path) == digest:
            os.utime(path, ns=(access_time, modification_time))


def _file_digest(path: Path) -> bytes:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.digest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Compile a Verilog design for FPGALab.")
    parser.add_argument("verilog", type=Path)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--top", default="top")
    parser.add_argument("--build-dir", default=Path("build/verilator"), type=Path)
    parser.add_argument("--verilator", default="verilator")
    ns = parser.parse_args()
    request = BuildRequest(ns.verilog, BoardProfile.load(ns.profile), ns.top, ns.build_dir, ns.verilator)
    print(VerilatorCompiler().build(request))


if __name__ == "__main__":
    main()
