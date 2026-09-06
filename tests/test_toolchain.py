"""Toolchain discovery and diagnostic coverage."""

from __future__ import annotations

import sys

import fpga_lab.toolchain as toolchain_module
from fpga_lab.toolchain import VerilatorToolchain


def test_build_tools_reports_resolved_executable_paths(tmp_path, monkeypatch):
    binary_directory = tmp_path / "bin"
    binary_directory.mkdir()
    suffix = ".exe" if sys.platform == "win32" else ""
    compiler = "c++" if sys.platform == "darwin" else "g++"
    make = binary_directory / f"make{suffix}"
    cxx = binary_directory / f"{compiler}{suffix}"
    make.touch()
    cxx.touch()
    monkeypatch.setenv("PATH", str(binary_directory))

    if sys.platform == "win32":
        python = binary_directory / "python.exe"
        python.touch()
        monkeypatch.setattr(toolchain_module, "_msys2_binary_directories", lambda: (binary_directory,))

    resolved = VerilatorToolchain(tmp_path / f"verilator{suffix}", "test").build_tools()

    assert resolved["make"] == make
    assert resolved[compiler] == cxx
    if sys.platform == "win32":
        assert resolved["python"] == python
