"""Offline bundle layout, integrity and extraction boundaries with synthetic inputs."""

import importlib.util
import json
from pathlib import Path
import sys
import tarfile

import pytest

import fpga_lab.private_toolchain as sdk_module


@pytest.fixture
def offline_inputs(tmp_path, monkeypatch):
    source = Path(__file__).parents[1] / "packaging/linux_toolchain/assemble.py"
    spec = importlib.util.spec_from_file_location("offline_assembler", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(sdk_module.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(sdk_module, "host_glibc", lambda: (2, 39))
    app = tmp_path / "app"
    (app / "_internal").mkdir(parents=True)
    (app / "FPGALab").write_text("synthetic application; not executed")
    (app / "FPGALab").chmod(0o755)
    (app / "_internal/license").write_text("retained notice")
    sdk = tmp_path / "toolchain"
    for relative in ("bin/verilator", "bin/make", "bin/g++", "bin/python3", "bin/perl", "bin/sh",
                     "rootfs/lib64/ld-linux-x86-64.so.2", "rootfs/usr/share/verilator/include/verilated.h"):
        path = sdk / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic resource")
        path.chmod(0o755)
    (sdk / "rootfs/lib").symlink_to("usr/lib")
    (sdk / "rootfs/usr/lib").mkdir()
    metadata = {"format": 1, "platform": "linux-x86_64", "status": "experimental-controlled-build",
                "recipe": {"id": "ubuntu24.04-x86_64-sdk1"}, "glibc": "glibc 2.39",
                "packages": {"verilator": "5.020-1", "make": "4.3", "g++": "13", "python3": "3.12", "perl": "5.38"}}
    (sdk / "toolchain.json").write_text(json.dumps(metadata))
    (sdk / "source-packages.json").write_text("{}")
    (sdk / "REDISTRIBUTION.txt").write_text("experimental source obligations")
    archive = tmp_path / "sdk.tar.gz"
    with tarfile.open(archive, "w:gz") as output:
        output.add(sdk, arcname="toolchain")
    return module, app, archive


def test_offline_bundle_preserves_layout_metadata_modes_and_notices(offline_inputs, tmp_path):
    module, app, archive = offline_inputs
    digest = module.sha256(archive)
    bundle = module.assemble(app, archive, digest, tmp_path / "output", "test-version", "revision")
    sdk = bundle / "toolchains/ubuntu24.04-x86_64-sdk1"
    assert sdk_module.PrivateSDK.load(sdk, expected_id=sdk.name).sdk_id == sdk.name
    assert (sdk / "rootfs/lib").is_symlink()
    assert (sdk / "REDISTRIBUTION.txt").read_text() == "experimental source obligations"
    assert (bundle / "_internal/license").read_text() == "retained notice"
    assert (bundle / "FPGALab").stat().st_mode & 0o111
    metadata = json.loads((bundle / "bundle.json").read_text())
    assert metadata["sdk_archive_sha256"] == digest and metadata["source_revision"] == "revision"
    combined = bundle.parent / "FPGALab-linux-x86_64-offline.tar.gz"
    assert combined.with_name(combined.name + ".sha256").read_text().startswith(module.sha256(combined))
    with tarfile.open(combined) as package:
        assert package.getmember("FPGALab/FPGALab").mode & 0o111
        assert package.getmember(f"FPGALab/toolchains/{sdk.name}/toolchain.json").isfile()
    assert not (app / "toolchains").exists()  # Inputs are not modified.
    # The CLI smoke fixture must be readable by FPGALab's real interface parser,
    # not merely syntactically valid to Verilator.
    from fpga_lab.verilog_interface import VerilogInterface
    path = Path(__file__).parents[1] / "packaging/linux_toolchain/smoke_offline.py"
    spec = importlib.util.spec_from_file_location("offline_smoke", path)
    smoke = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(smoke)
    source = tmp_path / "main.v"
    source.write_text(smoke.PROBE_VERILOG)
    profile = VerilogInterface.discover(source).profile()
    assert profile.inputs == {"clk": 1, "stimulus": 8}
    assert profile.outputs == {"result": 8, "count": 8} and profile.clock_name == "clk"


def test_offline_assembly_rejects_corruption_and_unsafe_archives(offline_inputs, tmp_path):
    module, app, archive = offline_inputs
    output = tmp_path / "never-created"
    with pytest.raises(ValueError, match="SHA-256"):
        module.assemble(app, archive, "0" * 64, output)
    assert not output.exists()
    for index, name in enumerate(("toolchain/../../escape", "/toolchain/absolute")):
        malformed = tmp_path / f"unsafe{index}.tar.gz"
        with tarfile.open(malformed, "w:gz") as package:
            package.addfile(tarfile.TarInfo(name))
        with pytest.raises(ValueError, match="archive path"):
            module.assemble(app, malformed, module.sha256(malformed), output)
        assert not output.exists() and not (tmp_path / "escape").exists()
    link = tmp_path / "unsafe-link.tar.gz"
    with tarfile.open(link, "w:gz") as package:
        member = tarfile.TarInfo("toolchain/escape")
        member.type, member.linkname = tarfile.SYMTYPE, "/etc/passwd"
        package.addfile(member)
    with pytest.raises(tarfile.FilterError):
        module.assemble(app, link, module.sha256(link), output)
    assert not output.exists()


def test_offline_assembly_never_overwrites_or_mixes_existing_toolchains(offline_inputs, tmp_path):
    module, app, archive = offline_inputs
    output = tmp_path / "existing"
    output.mkdir()
    (output / "keep").write_text("user data")
    with pytest.raises(ValueError):
        module.assemble(app, archive, module.sha256(archive), output)
    assert (output / "keep").read_text() == "user data"
    (app / "toolchains").mkdir()
    with pytest.raises(ValueError, match="already contains"):
        module.assemble(app, archive, module.sha256(archive), tmp_path / "new")
