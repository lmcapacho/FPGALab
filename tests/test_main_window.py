"""Critical main-window workflows and project selection."""

from __future__ import annotations

import os
import json
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QSettings, pyqtSignal
from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox, QWidget

from fpga_lab.lab_workspace import LabWorkspace
from fpga_lab.main_window import FPGALabMainWindow, LabManagerDialog
from fpga_lab.profile import BoardProfile


_APPLICATION = QApplication.instance() or QApplication([])


def test_main_window_stays_open_when_the_active_lab_cannot_close(tmp_path):
    class RefusingLab(QWidget):
        allow_close = False

        def closeEvent(self, event):
            event.accept() if self.allow_close else event.ignore()

    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    window = FPGALabMainWindow(LabWorkspace(tmp_path / "labs", settings))
    lab = RefusingLab()
    window.set_lab(lab)
    window.show()
    _APPLICATION.processEvents()

    assert window.close() is False
    assert window.isVisible()

    lab.allow_close = True
    assert window.close() is True
    window.deleteLater()


def test_board_selector_persists_and_supplies_controller_board_id(tmp_path, monkeypatch):
    from fpga_lab import app as app_module

    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    workspace = LabWorkspace(tmp_path / "labs", settings)
    packages = [
        SimpleNamespace(board_id="alhambra_ii", definition=SimpleNamespace(board_id="alhambra-ii", label="Alhambra II", clock_hz=12_000_000)),
        SimpleNamespace(board_id="test_board", definition=SimpleNamespace(board_id="test-board", label="Test Board", clock_hz=1_000_000)),
    ]

    class Catalog:
        def __init__(self):
            self.packages = packages

        def get(self, board_id):
            return next(package for package in packages if package.board_id == board_id)

        def resolve(self, identifier):
            return next(package for package in packages if identifier in (package.board_id, package.definition.board_id))

    class FakeLab(QWidget):
        def __init__(self, *args, **kwargs):
            super().__init__()
            self.board_id = kwargs["board_id"]
            self._lab_file = kwargs["lab_file"]

    monkeypatch.setattr(app_module, "FPGAVirtualLab", FakeLab)
    window = FPGALabMainWindow(workspace, settings=settings, board_catalog=Catalog())
    controller = app_module.ApplicationController(
        _APPLICATION, window,
        SimpleNamespace(cache_dir=tmp_path / "cache", clock_hz=None, ui_refresh_hz=None,
                        observation_hz=None, profile=None),
    )
    window.select_board("test_board")

    assert controller._board_id == "test_board"
    assert window.active_lab().board_id == "test_board"
    assert settings.value(window.BOARD_KEY) == "test_board"
    assert workspace.board_id(window.selected_lab()) == "test-board"
    window.set_project_loading(True)
    assert not window._board.isEnabled()
    window.set_project_loading(False)
    window.close()

    restored = FPGALabMainWindow(workspace, settings=settings, board_catalog=Catalog())
    assert restored.selected_board_id() == "test_board"
    restored.close()

    other = workspace.create("Other", board_id="alhambra-ii")
    next_window = FPGALabMainWindow(workspace, settings=settings, board_catalog=Catalog())
    next_window.set_lab(FakeLab(lab_file=next_window.selected_lab(), board_id="test_board"))
    next_controller = app_module.ApplicationController(
        _APPLICATION, next_window,
        SimpleNamespace(cache_dir=tmp_path / "cache", clock_hz=None, ui_refresh_hz=None,
                        observation_hz=None, profile=None),
    )
    next_window._set_selected_lab(other.path, notify=True)
    assert next_window.selected_board_id() == "alhambra_ii"
    assert next_controller._board_id == "alhambra_ii"
    assert next_window.active_lab().board_id == "alhambra_ii"
    assert workspace.board_id(other.path) == "alhambra-ii"
    next_window.close()


def test_lab_without_board_uses_default_and_unknown_board_is_not_rewritten(tmp_path, monkeypatch):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    workspace = LabWorkspace(tmp_path / "labs", settings)
    legacy = workspace.create("Legacy").path
    raw = json.loads(legacy.read_text(encoding="utf-8"))
    del raw["metadata"]["board_id"]
    legacy.write_text(json.dumps(raw), encoding="utf-8")
    workspace.remember_selected(legacy)

    window = FPGALabMainWindow(workspace, settings=settings)
    assert window.selected_board_id() == "alhambra_ii"

    unknown = workspace.create("Unknown", board_id="future-board").path
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args))
    window._set_selected_lab(unknown, notify=True)
    assert window.selected_lab() == legacy.resolve()
    assert workspace.board_id(unknown) == "future-board"
    assert warnings
    window.close()


def test_cached_model_is_closed_before_loading_same_library_again(tmp_path, monkeypatch):
    from fpga_lab import app as app_module

    events: list[str] = []

    class FakeLab(QWidget):
        status_changed = pyqtSignal(str)
        clock_performance_changed = pyqtSignal(float, float)

        def __init__(self, *_args, **_kwargs):
            super().__init__()

        def workbench_history(self):
            return None

        def start_simulation(self):
            events.append("start")

        def closeEvent(self, event):
            events.append("close")
            event.accept()

    def load_model(_library, _profile):
        events.append("load")
        assert events[0] == "close"
        return object()

    monkeypatch.setattr(app_module, "FPGAVirtualLab", FakeLab)
    monkeypatch.setattr(app_module, "VerilatorSimulation", load_model)
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    window = FPGALabMainWindow(LabWorkspace(tmp_path / "labs", settings))
    window.set_lab(FakeLab())
    controller = app_module.ApplicationController(
        _APPLICATION, window,
        SimpleNamespace(cache_dir=tmp_path / "cache", clock_hz=None, ui_refresh_hz=None,
                        observation_hz=None, profile=None),
    )
    project = SimpleNamespace(pcf=None, ice_file=Path(tmp_path / "echo.ice"))
    profile = BoardProfile("test", {"clk": 1}, {"tx": 1}, {}, "clk")
    controller._pending_run = app_module.PendingProjectRun(project, profile, "top", {}, {})
    artifact = SimpleNamespace(library=tmp_path / "libecho.so", reused=True,
                               incremental=False, compatibility_mode=False)

    controller._complete_build(artifact)

    assert events[:2] == ["close", "load"]
    assert "start" in events
    window.close()
    window.deleteLater()


def test_clock_indicator_reserves_space_before_actual_frequency_arrives(tmp_path):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    window = FPGALabMainWindow(LabWorkspace(tmp_path / "labs", settings))

    window.set_clock_performance(12_000_000)
    reserved_width = window._clock_status.minimumWidth()
    window.set_clock_performance(12_000_000, 8_750_000)

    assert window._clock_status.minimumWidth() == reserved_width
    assert window._clock_status.sizeHint().width() <= reserved_width
    window.close()
    window.deleteLater()


def test_deleting_the_active_lab_immediately_selects_the_starter_lab(tmp_path, monkeypatch):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    workspace = LabWorkspace(tmp_path / "workspace", settings)
    active = workspace.create("Active")
    workspace.remember_selected(active.path)
    dialog = LabManagerDialog(workspace, active.path)
    replacements: list[object] = []
    dialog.active_lab_changed.connect(replacements.append)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )

    dialog._delete_lab()

    starter = workspace.ensure_default().resolve()
    assert active.path.exists() is False
    assert replacements == [starter]
    assert dialog.selected_lab().resolve() == starter
    dialog.close()
    dialog.deleteLater()


def test_model_changing_controls_are_locked_while_running(tmp_path):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    window = FPGALabMainWindow(LabWorkspace(tmp_path / "labs", settings))

    window.set_simulation_running(True)

    assert window._run_button.isEnabled() is False
    assert window._stop_button.isEnabled() is True
    assert window._browse_button.isEnabled() is False
    assert window._recent.isEnabled() is False
    assert window._lab_button.isEnabled() is False
    assert window._simulation_settings_button.isEnabled() is False
    assert window._language.isEnabled() is True
    assert window._toolchain_button.isEnabled() is True

    window.set_simulation_running(False)

    assert window._run_button.isEnabled() is True
    assert window._stop_button.isEnabled() is False
    assert window._browse_button.isEnabled() is True
    assert window._recent.isEnabled() is True
    assert window._lab_button.isEnabled() is True
    assert window._simulation_settings_button.isEnabled() is True
    window.close()
    window.deleteLater()


def test_browse_opens_last_project_folder_across_sessions(tmp_path, monkeypatch):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    project_dir = tmp_path / "designs"
    project_dir.mkdir()
    project = project_dir / "example.ice"
    project.write_text("{}", encoding="utf-8")
    workspace = LabWorkspace(tmp_path / "labs", settings)
    first = FPGALabMainWindow(workspace, settings=settings)
    first.set_project_path(project)
    first.close()
    first.deleteLater()

    opened_from = []
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda parent, title, directory, file_filter: (opened_from.append(directory) or "", ""))
    second = FPGALabMainWindow(workspace, settings=settings)
    second._browse()
    assert opened_from == [str(project_dir)]
    second.close()
    second.deleteLater()

    project.unlink()
    third = FPGALabMainWindow(workspace, settings=settings)
    third._browse()
    assert opened_from[-1] == str(project_dir)
    third.close()
    third.deleteLater()


def test_about_dialog_identifies_the_maintainer_license_and_source(tmp_path, monkeypatch):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    window = FPGALabMainWindow(LabWorkspace(tmp_path / "labs", settings))
    dialogs: list[QMessageBox] = []
    monkeypatch.setattr(QMessageBox, "exec", lambda dialog: dialogs.append(dialog))

    window._show_about()

    assert len(dialogs) == 1
    text = dialogs[0].text()
    assert "Luis Miguel Capacho" in text
    assert "Affero" in text
    assert "https://github.com/lmcapacho/FPGALab" in text
    assert window._about_button.accessibleName()
    window.close()
    window.deleteLater()
