"""Persistence coverage for reusable laboratory selection."""

from __future__ import annotations

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
