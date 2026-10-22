"""Toolchain discovery and diagnostic coverage."""

from __future__ import annotations

import sys
import json
from pathlib import Path

import pytest

import fpga_lab.toolchain as toolchain_module
import fpga_lab.private_toolchain as sdk_module
from fpga_lab.toolchain import VerilatorToolchain


@pytest.fixture
def sdk_layout(tmp_path, monkeypatch):
    for variable in ("FPGALAB_VERILATOR", "FPGALAB_OSS_CAD_SUITE", "OSS_CAD_SUITE"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(sdk_module.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(sdk_module, "host_glibc", lambda: (2, 39))
    bundled, user = tmp_path / "portable/toolchains", tmp_path / "data/toolchains"
    monkeypatch.setattr(toolchain_module, "bundled_toolchains_root", lambda: bundled)
    monkeypatch.setattr(toolchain_module, "user_toolchains_root", lambda: user)
    monkeypatch.setattr(toolchain_module, "_apio_suite_roots", lambda: ())
    monkeypatch.setattr(toolchain_module.shutil, "which", lambda _: None)

    def create(base, sdk_id="ubuntu24.04-x86_64-sdk1"):
        root = base / sdk_id
        for relative in ("bin/verilator", "bin/make", "bin/g++", "bin/python3", "bin/perl", "bin/sh",
                         "rootfs/lib64/ld-linux-x86-64.so.2", "rootfs/usr/share/verilator/include/verilated.h"):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("synthetic fixture; never executed")
            path.chmod(0o755)
        metadata = {"format": 1, "status": "experimental-controlled-build", "platform": "linux-x86_64",
                    "recipe": {"id": sdk_id}, "glibc": "glibc 2.39",
                    "packages": {"verilator": "5.020-1", "make": "4.3", "g++": "13", "python3": "3.12", "perl": "5.38"}}
        (root / "toolchain.json").write_text(json.dumps(metadata))
        return root

    return bundled, user, create


def test_private_sdk_priority_environment_and_explicit_overrides(sdk_layout, monkeypatch):
    bundled, user, create = sdk_layout
    portable = create(bundled)
    installed = create(user, "ubuntu24.04-x86_64-sdk2")
    monkeypatch.setenv("PATH", "/external/bin")
    for variable in ("LD_LIBRARY_PATH", "LD_PRELOAD", "CC", "CXX", "MAKEFLAGS", "CPATH", "VERILATOR_ROOT"):
        monkeypatch.setenv(variable, "/external/value")
    resolved = toolchain_module.resolve_verilator()
    assert resolved.sdk.root == portable
    assert resolved.environment()["PATH"] == str(portable / "bin")
    assert resolved.environment()["VERILATOR_ROOT"] == str(portable / "rootfs/usr/share/verilator")
    for variable in ("LD_LIBRARY_PATH", "LD_PRELOAD", "CC", "CXX", "MAKEFLAGS", "CPATH"):
        assert variable not in resolved.environment()
    assert resolved.build_tools() == {name: portable / "bin" / name for name in ("make", "g++")}
    assert resolved.make_variables() == ("CXX=g++",)
    assert sdk_module.os.environ["PATH"] == "/external/bin"  # The GUI's environment is unchanged.
    monkeypatch.setenv("FPGALAB_VERILATOR", str(installed / "bin/verilator"))
    assert toolchain_module.resolve_verilator().sdk.root == installed
    monkeypatch.delenv("FPGALAB_VERILATOR")
    external = user.parent / "external"
    (external / "bin").mkdir(parents=True)
    (external / "bin/verilator").touch()
    monkeypatch.setenv("FPGALAB_OSS_CAD_SUITE", str(external))
    assert toolchain_module.resolve_verilator().suite_root == external
    # An explicit broken SDK is an error, never a silent switch to another compiler.
    (installed / "bin/g++").unlink()
    monkeypatch.setenv("FPGALAB_VERILATOR", str(installed / "bin/verilator"))
    with pytest.raises(sdk_module.SDKValidationError):
        toolchain_module.resolve_verilator()


def test_private_sdk_rejects_incompatible_and_incomplete_candidates_with_fallback(sdk_layout, monkeypatch):
    bundled, user, create = sdk_layout
    good = create(user)
    for index, changes in enumerate(({"format": 99}, {"platform": "windows-x86_64"},
                                      {"glibc": "glibc 2.40"}, {"packages": {}}, {"status": "unknown"})):
        root = create(bundled, f"bad-sdk{index}")
        metadata = root / "toolchain.json"
        data = json.loads(metadata.read_text())
        data.update(changes)
        metadata.write_text(json.dumps(data))
    incomplete = create(bundled, "incomplete")
    (incomplete / "bin/make").unlink()
    malformed = create(bundled, "malformed")
    (malformed / "toolchain.json").write_text("not JSON")
    mismatch = create(bundled, "wrong-directory-id")
    data = json.loads((mismatch / "toolchain.json").read_text())
    data["recipe"]["id"] = "different-id"
    (mismatch / "toolchain.json").write_text(json.dumps(data))
    escaped = create(bundled, "escaped-resource")
    outside = user.parent / "external-resource"
    outside.write_text("not part of SDK")
    (escaped / "bin/g++").unlink()
    (escaped / "bin/g++").symlink_to(outside)
    result = toolchain_module.resolve_verilator()
    assert result.sdk.root == good and len(result.diagnostics) == 9
    monkeypatch.setattr(sdk_module, "host_glibc", lambda: None)
    monkeypatch.setattr(toolchain_module.shutil, "which", lambda _: "/external/verilator")
    fallback = toolchain_module.resolve_verilator()
    assert fallback.sdk is None and len(fallback.diagnostics) == 10
    assert fallback.executable == Path("/external/verilator")
    monkeypatch.setattr(toolchain_module.shutil, "which", lambda _: None)
    with pytest.raises(toolchain_module.ToolchainNotFoundError, match="bad-sdk"):
        toolchain_module.resolve_verilator()


def test_sdk_paths_are_independent_of_cwd_and_frozen_internal_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "custom-data"))
    assert sdk_module.user_toolchains_root() == tmp_path / "custom-data/FPGALab/toolchains"
    monkeypatch.setenv("XDG_DATA_HOME", "relative/invalid")
    assert sdk_module.user_toolchains_root() == Path.home() / ".local/share/FPGALab/toolchains"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "portable/FPGALab"))
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "unrelated-extraction"), raising=False)
    monkeypatch.chdir(tmp_path)
    assert sdk_module.bundled_toolchains_root() == tmp_path / "portable/toolchains"
    monkeypatch.setattr(sys, "frozen", False)
    assert sdk_module.bundled_toolchains_root() is None


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
