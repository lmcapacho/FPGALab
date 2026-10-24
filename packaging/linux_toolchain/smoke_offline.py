#!/usr/bin/env python3
"""Probe a packaged GUI/native build without SDK overrides or host PATH tools."""

import argparse
import ctypes
import json
import os
from pathlib import Path
import subprocess
import time


PROBE_VERILOG = """module main(input clk, input [7:0] stimulus,
output [7:0] result, output reg [7:0] count);
initial count = 0;
assign result = stimulus ^ 8'hA5;
always @(posedge clk) count <= count + 1;
endmodule
"""


def probe(bundle, workspace, timeout=120):
    bundle, workspace = bundle.resolve(), workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=False)
    source = workspace / "ice-build/probe/main.v"
    source.parent.mkdir(parents=True)
    source.write_text(PROBE_VERILOG, encoding="utf-8")
    ice = workspace / "probe.ice"
    ice.write_text("{}", encoding="utf-8")
    environment = os.environ.copy()
    for variable in ("FPGALAB_VERILATOR", "FPGALAB_OSS_CAD_SUITE", "OSS_CAD_SUITE",
                     "FPGALAB_PERIPHERALS_DIR", "LD_LIBRARY_PATH", "LD_PRELOAD"):
        environment.pop(variable, None)
    environment.update(PATH="", QT_QPA_PLATFORM="offscreen", XDG_DATA_HOME=str(workspace / "data"),
                       XDG_CONFIG_HOME=str(workspace / "config"), XDG_CACHE_HOME=str(workspace / "cache"),
                       FPGALAB_WORKSPACE=str(workspace / "labs"))
    cache = workspace / "build-cache"
    log_path = workspace / "application.log"
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen([str(bundle / "FPGALab"), "--ice", str(ice), "--cache-dir", str(cache),
                                    "--clock-hz", "1000"], cwd=workspace, env=environment,
                                   stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + timeout
            library = None
            while time.monotonic() < deadline and process.poll() is None:
                manifests = list(cache.glob("*/manifest.json"))
                if manifests:
                    entry = manifests[0]
                    library = entry.parent / json.loads(entry.read_text())["library"]
                    break
                time.sleep(0.25)
            if library is None:
                raise RuntimeError(f"Packaged build did not finish; inspect {log_path}")
            sdk_id = json.loads((bundle / "bundle.json").read_text())["sdk_id"]
            sdk_root = str(bundle / "toolchains" / sdk_id / "rootfs/usr/share/verilator")
            makefiles = cache.glob("_incremental/*/obj_dir/Vmain.mk")
            if not any(sdk_root in path.read_text() for path in makefiles):
                raise RuntimeError("Generated Makefile does not identify the bundled SDK")
            # Give queued GUI completion handlers time to load/start the model.
            time.sleep(1)
            if process.poll() is not None:
                raise RuntimeError(f"Packaged app exited after build; inspect {log_path}")
            native = ctypes.CDLL(str(library))
            native.sim_set_stimulus.argtypes = [ctypes.c_uint64]
            native.sim_get_result.restype = ctypes.c_uint64
            native.sim_get_count.restype = ctypes.c_uint64
            native.run_cycles.argtypes = [ctypes.c_uint64]
            native.init_sim()
            try:
                native.sim_set_stimulus(0x3C)
                native.eval_sim()
                assert native.sim_get_result() == 0x99
                native.run_cycles(12)
                assert native.sim_get_count() == 12
                native.reset_sim()
                native.run_cycles(2)
                assert native.sim_get_count() == 2
            finally:
                native.close_sim()
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    receipt = {"checks": ["packaged-startup", "automatic-sdk", "empty-host-path", "native-abi", "reset"],
               "scope": "Headless package test; clean desktop and network isolation require separate validation"}
    (workspace / "validation.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print("PASS: packaged startup, automatic SDK discovery, compilation and native ABI without host PATH tools")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--work-dir", required=True, type=Path)
    args = parser.parse_args()
    probe(args.bundle, args.work_dir)
