"""Persistence coverage for reusable laboratory selection."""

from __future__ import annotations

import json
import pytest

from PyQt6.QtCore import QSettings

from fpga_lab.lab_workspace import LabWorkspace


def test_workspace_restores_the_last_selected_lab(tmp_path):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    workspace = LabWorkspace(tmp_path / "workspace", settings)
    first = workspace.ensure_default()
    second = workspace.create("Traffic demo").path

    workspace.remember_selected(second)

    restored = LabWorkspace(tmp_path / "workspace", settings)
    assert restored.last_selected() == second
    assert restored.last_selected() != first


def test_lab_board_metadata_is_read_and_updated_without_losing_content(tmp_path):
    workspace = LabWorkspace(tmp_path / "workspace")
    lab = workspace.create("Board test", board_id="test-board").path
    raw = json.loads(lab.read_text(encoding="utf-8"))
    raw["custom"] = {"keep": True}
    lab.write_text(json.dumps(raw), encoding="utf-8")

    assert workspace.board_id(lab) == "test-board"
    workspace.set_board_id(lab, "alhambra-ii")
    updated = json.loads(lab.read_text(encoding="utf-8"))
    assert updated["metadata"]["board_id"] == "alhambra-ii"
    assert updated["custom"] == {"keep": True}


def test_lab_clock_override_is_optional_and_board_change_restores_board_default(tmp_path):
    workspace = LabWorkspace(tmp_path / "workspace")
    lab = workspace.create("Clock test").path
    assert workspace.clock_override_hz(lab) is None

    workspace.set_clock_override_hz(lab, 25_175_000)
    assert workspace.clock_override_hz(lab) == 25_175_000
    workspace.set_board_id(lab, "another-board")
    assert workspace.clock_override_hz(lab) is None

    workspace.set_clock_override_hz(lab, 8_000_000)
    workspace.set_clock_override_hz(lab, None)
    assert workspace.clock_override_hz(lab) is None


@pytest.mark.parametrize("invalid", [True, 0, -1, "12000000", 1_000_000_001])
def test_lab_rejects_invalid_clock_overrides(tmp_path, invalid):
    workspace = LabWorkspace(tmp_path / "workspace")
    lab = workspace.create("Invalid clock").path
    with pytest.raises(ValueError):
        workspace.set_clock_override_hz(lab, invalid)


def test_workspace_falls_back_when_the_last_lab_no_longer_exists(tmp_path):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    workspace = LabWorkspace(tmp_path / "workspace", settings)
    selected = workspace.create("Temporary").path
    workspace.remember_selected(selected)
    selected.unlink()

    assert workspace.last_selected() == workspace.ensure_default()


def test_workspace_deletes_a_user_lab_but_keeps_the_starter_lab(tmp_path):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    workspace = LabWorkspace(tmp_path / "workspace", settings)
    starter = workspace.ensure_default()
    custom = workspace.create("Disposable").path

    assert workspace.delete(custom) is True
    assert custom.exists() is False
    assert workspace.delete(starter) is False
    assert starter.exists() is True


def test_workspace_duplicates_and_renames_a_user_lab(tmp_path):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    workspace = LabWorkspace(tmp_path / "workspace", settings)
    original = workspace.create("Counter Lab")

    duplicate = workspace.duplicate(original.path)
    renamed = workspace.rename(duplicate.path, "Counter Variations Lab")

    assert duplicate.path != original.path
    assert duplicate.name == "Counter Copy"
    assert duplicate.path.exists() is False
    assert renamed.name == "Counter Variations Lab"
    assert renamed.path.exists() is True


def test_workspace_base_name_removes_only_a_trailing_lab_suffix():
    assert LabWorkspace.base_name("Display Lab") == "Display"
    assert LabWorkspace.base_name("Laboratory") == "Laboratory"


def test_workspace_exports_and_imports_a_portable_lab(tmp_path):
    source_settings = QSettings(str(tmp_path / "source.ini"), QSettings.Format.IniFormat)
    source_workspace = LabWorkspace(tmp_path / "source-workspace", source_settings)
    original = source_workspace.create("Traffic Demo")
    raw = json.loads(original.path.read_text(encoding="utf-8"))
    raw["peripherals"].append({
        "id": "led_1",
        "type": "led",
        "connections": {"anode": "D0"},
        "properties": {"position": [20, 30]},
    })
    original.path.write_text(json.dumps(raw), encoding="utf-8")
    exported = source_workspace.export_lab(original.path, tmp_path / "shared-lab")

    target_settings = QSettings(str(tmp_path / "target.ini"), QSettings.Format.IniFormat)
    target_workspace = LabWorkspace(tmp_path / "target-workspace", target_settings)
    imported = target_workspace.import_lab(exported)

    assert exported.name == "shared-lab.lab"
    assert imported.name == "Traffic Demo"
    assert imported.path.parent == target_workspace.labs_dir
    assert json.loads(imported.path.read_text(encoding="utf-8"))["peripherals"] == raw["peripherals"]


def test_workspace_import_uses_a_unique_name_without_overwriting(tmp_path):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    workspace = LabWorkspace(tmp_path / "workspace", settings)
    existing = workspace.create("Shared")
    portable = tmp_path / "shared.lab.json"
    portable.write_text('{"metadata":{"name":"Shared"},"peripherals":[]}', encoding="utf-8")

    imported = workspace.import_lab(portable)

    assert existing.path.exists()
    assert imported.path != existing.path
    assert imported.name == "Shared 2"


def test_workspace_rejects_an_invalid_import(tmp_path):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    workspace = LabWorkspace(tmp_path / "workspace", settings)
    invalid = tmp_path / "invalid.lab.json"
    invalid.write_text('{"peripherals":[{"id":"led_1"}]}', encoding="utf-8")

    try:
        workspace.import_lab(invalid)
    except ValueError as error:
        assert "valid id and type" in str(error)
    else:
        raise AssertionError("Invalid Labs must not be imported")


def test_workspace_discovers_legacy_lab_json_files(tmp_path):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    labs_dir = tmp_path / "workspace" / "labs"
    labs_dir.mkdir(parents=True)
    legacy = labs_dir / "legacy.lab.json"
    legacy.write_text('{"metadata":{"name":"Legacy"},"peripherals":[]}', encoding="utf-8")

    workspace = LabWorkspace(tmp_path / "workspace", settings)

    assert legacy in {descriptor.path for descriptor in workspace.labs()}
    assert workspace.create("New Format").path.suffix == ".lab"
