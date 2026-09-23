"""Local installation does not overwrite or trust archive paths."""

from pathlib import Path
import zipfile

import pytest

from fpga_lab.peripherals.catalog import load_catalog
from fpga_lab.peripherals.install import install_package, uninstall_package


EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "peripherals" / "simple_relay"


def test_install_folder_and_refuse_replacement(tmp_path):
    root = tmp_path / "installed"
    assert install_package(EXAMPLE, destination_root=root) == "simple_relay"
    assert (root / "simple_relay" / "manifest.json").is_file()
    with pytest.raises(ValueError, match="already installed"):
        install_package(EXAMPLE, destination_root=root)
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
    assert install_package(archive, destination_root=root) == "simple_relay"
    assert (root / "simple_relay" / "manifest.json").is_file()


def test_reject_zip_traversal(tmp_path):
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("simple_relay/manifest.json", "{}")
        zipped.writestr("simple_relay/../../escape", "bad")
    with pytest.raises(ValueError, match="unsafe path"):
        install_package(archive, destination_root=tmp_path / "installed")
    assert not (tmp_path / "escape").exists()
