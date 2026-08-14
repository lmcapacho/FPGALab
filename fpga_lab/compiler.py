"""Compilación asíncrona y reproducible de Verilog a biblioteca compartida."""

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


class VerilatorCompiler:
    """Construye una .so/.dll sin shell; apto para ejecutarse desde QProcess."""

    def prepare(self, request: BuildRequest) -> tuple[Path, list[str]]:
        verilog = request.verilog.resolve()
        if not verilog.is_file():
            raise FileNotFoundError(verilog)
        if not shutil.which(request.verilator) and not Path(request.verilator).is_file():
            raise FileNotFoundError(f"No se encontró Verilator: {request.verilator}")

        build_dir = request.build_dir.resolve()
        obj_dir = build_dir / "obj_dir"
        obj_dir.mkdir(parents=True, exist_ok=True)
        wrapper = build_dir / "sim_main.cpp"
        wrapper.write_text(render_cpp_wrapper(request.profile, f"V{request.top_module}"), encoding="utf-8")

        library = shared_library_name(f"V{request.top_module}_shared")
        # --exe usa el Makefile de Verilator. -shared y -fPIC convierten ese
        # objetivo (sin main()) en una biblioteca cargable por ctypes.
        args = [
            "--cc", str(verilog), "--top-module", request.top_module, "--prefix", f"V{request.top_module}",
            "--Mdir", str(obj_dir), "-O3", "--exe", str(wrapper), "--build", "-j", "0", "-MAKEFLAGS", "OPT_FAST=-O3",
            "-CFLAGS", "-O3 -fPIC -march=native", "-LDFLAGS", "-shared", "-o", library,
        ]
        return obj_dir / library, args

    def build(self, request: BuildRequest) -> Path:
        target, args = self.prepare(request)
        subprocess.run([request.verilator, *args], check=True, cwd=request.build_dir.resolve())
        if not target.exists():
            raise RuntimeError(f"Verilator terminó pero no produjo {target}")
        return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Compila un diseño Verilog para FPGALab.")
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
