from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import fpga_lab.build_cache as cache_module
from fpga_lab.build_cache import VerilatorBuildCache
from fpga_lab.compiler import shared_library_name
from fpga_lab.ice_project import IcestudioProject
from fpga_lab.profile import BoardProfile


class _Toolchain:
    executable = Path("/tools/verilator")

    def activate_runtime(self):
        return None

    def validate_build_prerequisites(self):
        return None

    def environment(self):
        return {}

    def make_variables(self):
        return ()


def test_changed_hdl_reuses_a_stable_incremental_workspace(tmp_path, monkeypatch):
    ice_file = tmp_path / "design.ice"
    ice_file.write_text("{}", encoding="utf-8")
    build_dir = tmp_path / "ice-build" / "design"
    build_dir.mkdir(parents=True)
    main_v = build_dir / "main.v"
    main_v.write_text("module main; endmodule\n", encoding="utf-8")
    project = IcestudioProject(ice_file, build_dir, main_v, None)
    profile = BoardProfile("Test", {}, {}, {}, None)
    build_directories: list[Path] = []

    monkeypatch.setattr(cache_module, "resolve_verilator", lambda _: _Toolchain())

    def fake_build(_compiler, request):
        build_directories.append(request.build_dir)
        library = request.build_dir / "obj_dir" / shared_library_name("Vmain_shared")
        library.parent.mkdir(parents=True, exist_ok=True)
        (library.parent / "Vmain.mk").write_text("generated", encoding="utf-8")
        library.write_bytes(f"build-{len(build_directories)}".encode())
        return library

    monkeypatch.setattr(cache_module.VerilatorCompiler, "build", fake_build)
    cache = VerilatorBuildCache(tmp_path / "cache")

    first = cache.build_or_reuse(project, profile, top_module="main")
    main_v.write_text("module main; wire changed; endmodule\n", encoding="utf-8")
    second = cache.build_or_reuse(project, profile, top_module="main")
    repeated = cache.build_or_reuse(project, profile, top_module="main")

    assert first.reused is False and first.incremental is False
    assert second.reused is False and second.incremental is True
    assert repeated.reused is True
    assert build_directories[0] == build_directories[1]
    assert first.fingerprint != second.fingerprint
    assert first.library.read_bytes() == b"build-1"
    assert second.library.read_bytes() == b"build-2"

    main_v.write_text("module main; wire third_version; endmodule\n", encoding="utf-8")
    third = cache.build_or_reuse(project, profile, top_module="main")

    assert third.incremental is True
    assert first.directory.exists() is False
    assert second.directory.exists() is True
    assert third.directory.exists() is True
    assert len(list((cache.root / "_incremental").iterdir())) == 1


def test_automatic_budget_is_bounded_and_reacts_to_low_disk_space(tmp_path, monkeypatch):
    cache = VerilatorBuildCache(tmp_path / "cache")
    cache.root.mkdir(parents=True)
    gibibyte = 1024 * 1024 * 1024
    monkeypatch.setattr(cache_module.shutil, "disk_usage", lambda _path: SimpleNamespace(total=20 * gibibyte, free=10 * gibibyte))
    assert cache.budget_bytes() == int(20 * gibibyte * 0.01)

    monkeypatch.setattr(cache_module.shutil, "disk_usage", lambda _path: SimpleNamespace(total=500 * gibibyte, free=1 * gibibyte))
    assert cache.budget_bytes() == 64 * 1024 * 1024
