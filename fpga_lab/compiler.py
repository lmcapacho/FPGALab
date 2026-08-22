"""Reproducible asynchronous compilation from Verilog to a shared library."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .cpp_wrapper import render_cpp_wrapper
from .profile import BoardProfile


class VerilatorBuildError(RuntimeError):
    """Verilator failure including its captured diagnostic output."""


def shared_library_name(stem: str = "Vtop_shared") -> str:
    if sys.platform == "win32":
        return f"{stem}.dll"
    if sys.platform == "darwin":
        return f"lib{stem}.dylib"
    return f"lib{stem}.so"


@dataclass(frozen=True)
class BuildRequest:
    verilog: Path
    profile: BoardProfile
    top_module: str = "top"
    build_dir: Path = Path("build/verilator")
    verilator: str = "verilator"
    environment: dict[str, str] | None = None
    make_variables: tuple[str, ...] = ()


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
        wrapper.write_text(render_cpp_wrapper(request.profile, f"V{request.top_module}"), encoding="utf-8")

        library = shared_library_name(f"V{request.top_module}_shared")
        # --exe writes a Makefile.  Building it in a separate process is
        # important on Windows: Verilator is native while Make runs in MSYS2.
        args = [
            "--cc", str(verilog), "--top-module", request.top_module, "--prefix", f"V{request.top_module}",
            "--Mdir", str(obj_dir), "-O3", "-Wno-fatal", "--exe", str(wrapper),
            "-CFLAGS", "-O3 -fPIC -march=native", "-LDFLAGS", "-shared", "-o", library,
        ]
        return obj_dir / library, args

    def build(self, request: BuildRequest) -> Path:
        target, args = self.prepare(request)
        self._run(
            [request.verilator, *args],
            cwd=request.build_dir.resolve(),
            environment=request.environment,
        )
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
        )
        if completed.returncode:
            output = completed.stdout.strip() or "Verilator did not provide diagnostic output."
            raise VerilatorBuildError(output)


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
