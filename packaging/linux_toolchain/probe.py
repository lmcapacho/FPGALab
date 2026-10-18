#!/usr/bin/env python3
"""Compile and execute FPGALab's actual ABI using an experimental Linux SDK."""

import argparse
import ctypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def prepare(sdk, workspace):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from fpga_lab.compiler import BuildRequest, VerilatorCompiler
    from fpga_lab.profile import BoardProfile
    workspace.mkdir(parents=True, exist_ok=False)
    verilog = workspace / "top.v"
    verilog.write_text("""module top(input clk, input [7:0] stimulus,
output [7:0] combinational, output reg [7:0] count = 0);
assign combinational = stimulus ^ 8'hA5;
always @(posedge clk) count <= count + 1;
endmodule
""", encoding="utf-8")
    profile = BoardProfile("SDK probe", {"clk": 1, "stimulus": 8}, {"combinational": 8, "count": 8}, {}, "clk")
    target, args = VerilatorCompiler().prepare(BuildRequest(
        verilog, profile, build_dir=workspace / "build", verilator=str(sdk / "bin/verilator"),
    ))
    state = {"sdk": str(sdk), "target": str(target), "args": args}
    (workspace / "probe.json").write_text(json.dumps(state), encoding="utf-8")


def run(workspace, sandboxed=False):
    if sandboxed:
        for forbidden in ("/usr/bin/g++", "/usr/bin/make", "/usr/bin/verilator", "/usr/include"):
            assert not Path(forbidden).exists(), f"Host build files are visible: {forbidden}"
    state = json.loads((workspace / "probe.json").read_text())
    sdk, target = Path(state["sdk"]), Path(state["target"])
    environment = os.environ.copy()
    environment["PATH"] = str(sdk / "bin")
    environment["VERILATOR_ROOT"] = str(sdk / "rootfs/usr/share/verilator")
    for variable in ("CC", "CXX", "MAKEFLAGS", "GCC_EXEC_PREFIX", "COMPILER_PATH", "LIBRARY_PATH", "CPATH", "CPLUS_INCLUDE_PATH", "C_INCLUDE_PATH"):
        environment.pop(variable, None)
    subprocess.run([str(sdk / "bin/verilator"), *state["args"]], cwd=workspace / "build", env=environment, check=True)
    for _ in range(2):
        subprocess.run([str(sdk / "bin/make"), "--silent", "-C", str(target.parent), "-f", "Vtop.mk", "-j2", "CXX=g++", "OPT_FAST=-O3"],
                       cwd=workspace / "build", env=environment, check=True)
    library = ctypes.CDLL(str(target))
    library.sim_set_stimulus.argtypes = [ctypes.c_uint64]
    library.run_cycles.argtypes = [ctypes.c_uint64]
    library.sim_get_combinational.restype = ctypes.c_uint64
    library.sim_get_count.restype = ctypes.c_uint64
    library.init_sim()
    try:
        library.sim_set_stimulus(0x3C)
        library.eval_sim()
        assert library.sim_get_combinational() == 0x99
        library.run_cycles(12)
        assert library.sim_get_count() == 12
        library.reset_sim()
        library.run_cycles(2)
        assert library.sim_get_count() == 2
    finally:
        library.close_sim()
    print("PASS: FPGALab ABI, combinational logic, clocked logic, Reset and repeated Make build")


def isolated(sdk, workspace):
    bwrap = shutil.which("bwrap")
    if bwrap is None:
        raise RuntimeError("Isolation requires bubblewrap on the maintainer machine; this is not a user dependency")
    command = [bwrap, "--unshare-all", "--die-with-parent", "--new-session", "--clearenv",
               "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
               "--dir", "/bin", "--ro-bind", str(Path("/bin/sh").resolve()), "/bin/sh",
               "--dir", "/usr/bin", "--ro-bind", "/usr/bin/env", "/usr/bin/env",
               "--dir", "/lib64", "--ro-bind", str(Path("/lib64/ld-linux-x86-64.so.2").resolve()), "/lib64/ld-linux-x86-64.so.2",
               "--dir", "/lib/x86_64-linux-gnu", "--ro-bind", str(Path("/lib/x86_64-linux-gnu/libc.so.6").resolve()), "/lib/x86_64-linux-gnu/libc.so.6",
               "--ro-bind", str(sdk), str(sdk), "--bind", str(workspace), str(workspace),
               "--ro-bind", str(Path(__file__).resolve()), "/probe.py", "--chdir", str(workspace),
               "--setenv", "PATH", str(sdk / "bin"), "--setenv", "HOME", "/tmp",
               "--", str(sdk / "bin/python3"), "/probe.py", "--run", "--sandboxed", "--work-dir", str(workspace)]
    subprocess.run(command, check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", type=Path)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--isolated", action="store_true")
    parser.add_argument("--run", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--sandboxed", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    workspace = args.work_dir.resolve()
    if args.run:
        run(workspace, args.sandboxed)
    else:
        if args.sdk is None:
            parser.error("--sdk is required")
        sdk = args.sdk.resolve()
        if any(character.isspace() for character in str(sdk) + str(workspace)):
            parser.error("This initial SDK prototype requires SDK/work paths without whitespace")
        prepare(sdk, workspace)
        if args.isolated:
            isolated(sdk, workspace)
        else:
            run(workspace)
