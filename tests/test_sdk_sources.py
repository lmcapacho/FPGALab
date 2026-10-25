"""Exact source collection, provenance and publication gates without APT or Docker."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def tools():
    path = Path(__file__).parents[1] / "packaging/linux_toolchain/container_build.py"
    spec = importlib.util.spec_from_file_location("sdk_source_build", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, module.source_tools()


@pytest.fixture
def source_fixture(tools, tmp_path, monkeypatch):
    build, sources = tools
    sdk, repository = tmp_path / "sdk", tmp_path / "context"
    sdk.mkdir()
    repository.mkdir()
    (repository / "fpga_lab").mkdir()
    (repository / "fpga_lab/example.py").write_text("# synthetic source\n")
    (repository / "packaging/linux_toolchain").mkdir(parents=True)
    (repository / "packaging/linux_toolchain/recipe.json").write_text('{"format": 1}')
    for name in build.CONTEXT_FILES:
        (repository / name).write_text("synthetic local input")
    provenance = {"format": 1, "git": {"revision": "fixture", "dirty": True},
                  "files": {path.relative_to(repository).as_posix(): sources.sha256(path)
                            for path in repository.rglob("*") if path.is_file()}}
    (repository / "provenance.json").write_text(json.dumps(provenance))
    inventory = {name: {"source": "demo", "version": "1:2.0-1", "copyright": f"notices/{name}"}
                 for name in ("libdemo", "demo-bin")}
    for item in inventory.values():
        path = sdk / item["copyright"]
        path.parent.mkdir(exist_ok=True)
        path.write_text("Copyright fixture")
    common = sdk / "rootfs/usr/share/common-licenses"
    common.mkdir(parents=True)
    (common / "GPL-3").write_text("synthetic license fixture")
    (sdk / "source-packages.json").write_text(json.dumps(inventory))
    (sdk / "toolchain.json").write_text(json.dumps({"recipe": {"id": "fixture-sdk2"}, "build_provenance": provenance}))
    payload = b"synthetic upstream archive; never extracted"
    import hashlib
    info = f"{hashlib.sha256(payload).hexdigest()} {len(payload)} demo_2.0.orig.tar.xz"
    dsc = ("-----BEGIN PGP SIGNED MESSAGE-----\nHash: SHA256\n\n"
           "Source: demo\nVersion: 1:2.0-1\nChecksums-Sha256:\n " + info +
           "\n-----BEGIN PGP SIGNATURE-----\nsynthetic signature\n").encode()
    files = {"demo_2.0.orig.tar.xz": payload, "demo_2.0-1.dsc": dsc}
    checksums = "\n".join(f" {hashlib.sha256(value).hexdigest()} {len(value)} {name}" for name, value in files.items())
    record = f"Package: demo\nVersion: 1:2.0-1\nChecksums-Sha256:\n{checksums}\n"
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        if command[0] == "apt-cache":
            return SimpleNamespace(stdout="Package: demo\nVersion: 9.0\n\n" + record)
        assert command == ["apt-get", "source", "--download-only", "--only-source", "demo=1:2.0-1"]
        for name, value in files.items():
            (kwargs["cwd"] / name).write_bytes(value)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(sources.subprocess, "run", run)
    return sdk, repository, files, record, calls


def test_source_collection_deduplicates_exact_versions_and_verifies_companion(tools, source_fixture, tmp_path):
    build, sources = tools
    sdk, repository, files, record, calls = source_fixture
    relocated = tmp_path / "relocated-sdk"
    sdk.rename(relocated)
    sdk = relocated
    output = tmp_path / "sdk-sources"
    manifest = sources.collect(sdk, output, repository)
    assert len(manifest["sources"]) == 1
    assert manifest["sources"][0]["binaries"] == ["demo-bin", "libdemo"]
    assert calls[-1][-1] == "demo=1:2.0-1"  # Never choose the newest available version.
    assert sources.verify_collection(sdk, output) == manifest
    incomplete = {**manifest, "sources": []}
    (output / "source-manifest.json").write_text(json.dumps(incomplete))
    with pytest.raises(ValueError, match="coverage"):
        build.archive_outputs(tmp_path)
    assert not list(tmp_path.glob("*.tar.gz"))
    (output / "source-manifest.json").write_text(json.dumps(manifest))
    build.archive_outputs(tmp_path)
    receipt = json.loads((tmp_path / "source-bundle.json").read_text())
    archive = tmp_path / receipt["sources"]["file"]
    checksum = receipt["sources"]["sha256"]
    assert checksum == sources.sha256(archive) and receipt["legal_approval"] is False
    assert receipt["sdk"]["sha256"] == sources.sha256(tmp_path / receipt["sdk"]["file"])
    assert json.loads((sdk / "toolchain.json").read_text())["source_bundle"] == receipt["sources"]
    assert archive.with_name(archive.name + ".sha256").read_text().startswith(checksum)
    with pytest.raises(ValueError, match="overwrite"):
        sources.archive_sources(output, archive)
    package = output / manifest["sources"][0]["directory"]
    (package / "demo_2.0.orig.tar.xz").write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="source changed"):
        sources.verify_collection(sdk, output)


def test_source_collection_fails_closed_on_missing_versions_checksums_and_coverage(tools, source_fixture, tmp_path):
    _, sources = tools
    sdk, repository, files, record, calls = source_fixture
    with pytest.raises(ValueError, match="unavailable"):
        sources.select_record(record, "demo", "2.0-2")
    with pytest.raises(ValueError, match="Conflicting"):
        sources.select_record(record + "\n" + record.replace("orig.tar.xz", "other.tar.xz"), "demo", "1:2.0-1")
    with pytest.raises(ValueError, match="SHA-256"):
        sources.file_records({"Checksums-Sha256": "0" * 64 + " 1 ../escape"})
    files["demo_2.0.orig.tar.xz"] = b"wrong"
    output = tmp_path / "failed"
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        sources.collect(sdk, output, repository)
    assert not (output / "source-manifest.json").exists()
    with pytest.raises(FileNotFoundError):
        sources.verify_collection(sdk, output)
    assert not (tmp_path / "sources.tar.gz").exists()


def test_sdk_context_records_real_inputs_without_git_history_or_local_installs(tools, tmp_path):
    build, sources = tools
    repository = tmp_path / "repo"
    repository.mkdir()
    for name in ("fpga_lab", "packaging/linux_toolchain", ".git", ".venv", "fpga_lab/__pycache__"):
        (repository / name).mkdir(parents=True, exist_ok=True)
    (repository / "fpga_lab/example.py").write_text("# current working tree\n")
    (repository / "fpga_lab/__pycache__/example.pyc").write_bytes(b"cache")
    (repository / "fpga_lab/.env").write_text("local secret; never copy")
    (repository / ".env").write_text("local secret; never copy")
    for name in build.CONTEXT_FILES:
        (repository / name).write_text("fixture")
    context = tmp_path / "context"
    context.mkdir()
    build.prepare_context(repository, context)
    provenance = json.loads((context / "provenance.json").read_text())
    assert provenance["files"]["fpga_lab/example.py"] == sources.sha256(repository / "fpga_lab/example.py")
    assert not (context / ".git").exists() and not (context / ".env").exists()
    assert not (context / ".venv").exists() and not (context / "fpga_lab/__pycache__").exists()
    assert not (context / "fpga_lab/.env").exists()
