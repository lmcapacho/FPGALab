"""Local installation does not overwrite or trust archive paths."""

from pathlib import Path
import json
import shutil
import zipfile

import pytest

from fpga_lab.peripherals.catalog import load_catalog
from fpga_lab.peripherals.install import _compare_versions, install_package, uninstall_package


EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "peripherals" / "simple_relay"


def test_install_folder_and_identical_reinstall(tmp_path):
    root = tmp_path / "installed"
    assert install_package(EXAMPLE, destination_root=root).action == "installed"
    assert (root / "simple_relay" / "manifest.json").is_file()
    assert install_package(EXAMPLE, destination_root=root).action == "unchanged"
    uninstall_package("simple_relay", destination_root=root)
    assert not (root / "simple_relay").exists()
    load_catalog.cache_clear()


def test_uninstall_rejects_outside_target(tmp_path):
    with pytest.raises(ValueError, match="Invalid peripheral id"):
        uninstall_package("../simple_relay", destination_root=tmp_path)


def test_install_zip(tmp_path):
    archive = tmp_path / "relay.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        for path in EXAMPLE.iterdir():
            if path.is_file():
                zipped.write(path, f"simple_relay/{path.name}")
    root = tmp_path / "installed"
    assert install_package(archive, destination_root=root).action == "installed"
    assert (root / "simple_relay" / "manifest.json").is_file()


def test_reject_zip_traversal(tmp_path):
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("simple_relay/manifest.json", "{}")
        zipped.writestr("simple_relay/../../escape", "bad")
    with pytest.raises(ValueError, match="unsafe path"):
        install_package(archive, destination_root=tmp_path / "installed")
    assert not (tmp_path / "escape").exists()


def _changed_package(tmp_path, version="1.1.0"):
    source = tmp_path / "source" / "simple_relay"
    shutil.copytree(EXAMPLE, source)
    manifest = source / "manifest.json"
    raw = json.loads(manifest.read_text())
    raw["package"]["version"] = version
    manifest.write_text(json.dumps(raw))
    return source


def test_update_requires_newer_version_and_confirmation(tmp_path):
    root = tmp_path / "installed"
    install_package(EXAMPLE, destination_root=root)
    original = (root / "simple_relay" / "manifest.json").read_bytes()
    newer = _changed_package(tmp_path)
    with pytest.raises(ValueError, match="requires confirmation"):
        install_package(newer, destination_root=root)
    assert install_package(newer, destination_root=root, confirm_update=lambda *_: False).action == "cancelled"
    assert (root / "simple_relay" / "manifest.json").read_bytes() == original
    confirmed = []
    result = install_package(newer, destination_root=root, confirm_update=lambda *args: confirmed.append(args) or True)
    assert result.action == "updated"
    assert confirmed == [("simple_relay", "1.0.1", "1.1.0")]
    assert json.loads((root / "simple_relay" / "manifest.json").read_text())["package"]["version"] == "1.1.0"
    assert install_package(newer, destination_root=root).action == "unchanged"


def test_reject_same_version_with_changed_files_and_downgrade(tmp_path):
    root = tmp_path / "installed"
    install_package(EXAMPLE, destination_root=root)
    for version in ("1.0.1", "0.9.0"):
        source = _changed_package(tmp_path / version, version)
        with pytest.raises(ValueError, match="newer package version"):
            install_package(source, destination_root=root, confirm_update=lambda *_: True)


def test_invalid_update_keeps_old_package(tmp_path):
    root = tmp_path / "installed"
    install_package(EXAMPLE, destination_root=root)
    source = _changed_package(tmp_path)
    (source / "off.svg").write_text("<svg")
    with pytest.raises(ValueError, match="Invalid SVG"):
        install_package(source, destination_root=root, confirm_update=lambda *_: True)
    assert (root / "simple_relay" / "off.svg").read_text() != "<svg"


def test_failed_replace_restores_previous_package(tmp_path, monkeypatch):
    root = tmp_path / "installed"
    install_package(EXAMPLE, destination_root=root)
    original = (root / "simple_relay" / "manifest.json").read_bytes()
    source = _changed_package(tmp_path)
    rename = Path.rename

    def fail_candidate(self, target):
        if self.name == "candidate":
            raise OSError("simulated replacement failure")
        return rename(self, target)

    monkeypatch.setattr(Path, "rename", fail_candidate)
    with pytest.raises(OSError, match="simulated replacement failure"):
        install_package(source, destination_root=root, confirm_update=lambda *_: True)
    assert (root / "simple_relay" / "manifest.json").read_bytes() == original


def test_semantic_version_precedence():
    assert _compare_versions("1.0.0", "1.0.0-rc.2") > 0
    assert _compare_versions("1.0.0-rc.10", "1.0.0-rc.2") > 0
    assert _compare_versions("1.0.1", "1.0.0") > 0
    assert _compare_versions("1.0.0+build2", "1.0.0+build1") == 0
