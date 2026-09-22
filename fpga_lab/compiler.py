"""Reproducible asynchronous compilation from Verilog to a shared library."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import signal
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .cpp_wrapper import render_cpp_wrapper
from .profile import BoardProfile


class VerilatorBuildError(RuntimeError):
    """Verilator failure including its captured diagnostic output."""


class BuildCancelled(RuntimeError):
    """The user closed FPGALab before the native build completed."""


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
    cancel_requested: Callable[[], bool] | None = None


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
        # One-file bundles unpack under a new _MEI directory on every launch.
        # Make dependency files must refer to sources in the persistent build
        # workspace, otherwise the next incremental build cannot find them.
        native = build_dir / "native"
        native.mkdir(exist_ok=True)
        for source in _native_source_dir().iterdir():
            if source.is_file() and source.suffix in {".cpp", ".h"}:
                _copy_if_changed(source, native / source.name)
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
            cancel_requested=request.cancel_requested,
        )
        _restore_unchanged_timestamps(generated_state)
        make = shutil.which("make", path=(request.environment or os.environ).get("PATH"))
        if make is None:
            raise RuntimeError("Verilator generated its Makefile but GNU Make was not found.")
        self._run(
            [make, "-C", str(target.parent), "-f", f"V{request.top_module}.mk", "-j", "OPT_FAST=-O3", *request.make_variables],
            cwd=request.build_dir.resolve(),
            environment=request.environment,
            cancel_requested=request.cancel_requested,
        )
        if not target.exists():
            raise RuntimeError(f"Verilator completed but did not produce {target}")
        return target

    @staticmethod
    def _run(
        command: list[str], *, cwd: Path, environment: dict[str, str] | None,
        cancel_requested: Callable[[], bool] | None = None,
    ) -> None:
        """Run one cancellable build phase and retain diagnostics on failure."""
        if cancel_requested is not None and cancel_requested():
            raise BuildCancelled("Build cancelled.")
        process = subprocess.Popen(
            command,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=environment,
            creationflags=_subprocess_creation_flags(),
            start_new_session=sys.platform != "win32",
        )
        while True:
            try:
                output, _ = process.communicate(timeout=0.1)
                break
            except subprocess.TimeoutExpired:
                if cancel_requested is not None and cancel_requested():
                    _terminate_process_tree(process)
                    raise BuildCancelled("Build cancelled.")
        if process.returncode:
            output = output.strip() or "Verilator did not provide diagnostic output."
            raise VerilatorBuildError(output)


def _subprocess_creation_flags() -> int:
    """Keep native build tools hidden behind the FPGALab progress UI on Windows."""
    if sys.platform == "win32":
        no_window = int(getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))
        process_group = int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200))
        return no_window | process_group
    return 0


def _terminate_process_tree(process: subprocess.Popen, timeout: float = 1.5) -> None:
    """Stop a compiler and its descendants without leaving orphan processes."""
    if process.poll() is not None:
        return
    if sys.platform == "win32":
        flags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
            check=False,
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
    try:
        process.wait(timeout=timeout)
        if sys.platform == "win32":
            return
    except subprocess.TimeoutExpired:
        if sys.platform == "win32":
            pass
    if sys.platform != "win32":
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                os.killpg(process.pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.05)
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)),
            check=False,
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()


def _write_if_changed(path: Path, content: str) -> None:
    """Preserve timestamps so Make can reuse an unchanged generated wrapper."""
    try:
        if path.read_text(encoding="utf-8") == content:
            return
    except FileNotFoundError:
        pass
    path.write_text(content, encoding="utf-8")


def _native_source_dir() -> Path:
    return Path(__file__).resolve().parent / "native"


def _copy_if_changed(source: Path, destination: Path) -> None:
    """Update workspace sources by content without invalidating unchanged objects."""
    content = source.read_bytes()
    try:
        if destination.read_bytes() == content:
            return
    except FileNotFoundError:
        pass
    destination.write_bytes(content)


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
