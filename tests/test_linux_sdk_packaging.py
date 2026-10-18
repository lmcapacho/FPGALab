"""Portable SDK packaging contracts without a local toolchain dependency."""

import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


@pytest.fixture
def builder():
    source = Path(__file__).parents[1] / "packaging/linux_toolchain/build.py"
    spec = importlib.util.spec_from_file_location("linux_sdk_builder", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sdk_dependency_closure_resolves_alternatives_virtuals_and_cycles(builder):
    records = {
        "compiler": {"dependencies": "runtime (>= 1), missing | make:any, awk"},
        "runtime": {"dependencies": "compiler"},
        "make": {"dependencies": ""},
        "mawk": {"dependencies": "", "provides": ["awk"]},
    }
    assert builder.dependency_closure(records, ["compiler"]) == ["compiler", "make", "mawk", "runtime"]
    records["runtime"]["dependencies"] = "not-installed"
    with pytest.raises(ValueError, match="Cannot resolve"):
        builder.dependency_closure(records, ["compiler"])


@pytest.mark.skipif(sys.platform != "linux", reason="Linux SDK launchers")
def test_sdk_compiler_launcher_relocates_and_isolates_search_paths(builder, tmp_path):
    sdk = tmp_path / "original"
    binaries = sdk / "rootfs/usr/bin"
    binaries.mkdir(parents=True)
    (sdk / "rootfs/usr/share/verilator/bin").mkdir(parents=True)
    (sdk / "rootfs/usr/lib/gcc/x86_64-linux-gnu/13").mkdir(parents=True)
    builder.write_executable(binaries / "g++", '#!/bin/sh\nprintf "%s\\n" "$@"\nprintf "CPATH=%s\\n" "${CPATH-unset}"\n')
    builder.create_launchers(sdk, sdk / "rootfs")
    relocated = tmp_path / "moved"
    shutil.move(str(sdk), relocated)
    result = subprocess.run([str(relocated / "bin/g++"), "input.cpp"],
                            env={"PATH": "", "CPATH": "/host/includes"}, check=True, capture_output=True, text=True)
    assert f"--sysroot={relocated}/rootfs" in result.stdout
    assert f"-B{relocated}/rootfs/usr/lib/gcc/x86_64-linux-gnu/13/" in result.stdout
    assert "input.cpp" in result.stdout and "CPATH=unset" in result.stdout
    assert str(sdk) not in result.stdout


def test_sdk_builder_never_overwrites_existing_output(builder, tmp_path):
    existing = tmp_path / "keep"
    existing.mkdir()
    marker = existing / "user-file"
    marker.write_text("preserve")
    if sys.platform == "linux":
        with pytest.raises(ValueError):
            builder.build(existing)
    assert marker.read_text() == "preserve"


def test_sdk_does_not_wrap_shared_plugins_and_archives_without_overwriting(builder, tmp_path):
    source = tmp_path / "sdk"
    source.mkdir()
    (source / "toolchain.json").write_text('{"format": 1}')
    executable = source / "cc1plus"
    plugin = source / "liblto_plugin.so"
    for path in (executable, plugin):
        path.write_bytes(b"\x7fELFtest")
        path.chmod(0o755)
    assert builder.is_executable_elf(executable)
    assert not builder.is_executable_elf(plugin)
    archive = tmp_path / "sdk.tar.gz"
    builder.archive_bundle(source, archive)
    assert archive.is_file() and archive.with_name("sdk.tar.gz.sha256").is_file()
    with pytest.raises(ValueError):
        builder.archive_bundle(source, archive)
