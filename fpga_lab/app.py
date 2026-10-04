"""Standalone FPGALab GUI entry point."""

from __future__ import annotations

import argparse
import json
import sys
from threading import Event
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QObject, QSettings, QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import QApplication, QMessageBox

from .board import DEFAULT_BOARD_ID, BoardDefinition, bundled_board_definition
from .branding import application_icon
from .build_cache import VerilatorBuildCache
from .compiler import BuildCancelled
from .ice_project import IcestudioProject, IcestudioProjectError
from .i18n import QtDialogTranslations, t
from .lab_workspace import LabWorkspace
from .main_window import FPGALabMainWindow
from .profile import BoardProfile, bundled_profile
from .profile_policy import apply_led_observed
from .project_pins import ProjectPinMap
from .signals import signal_reference
from .simulation import VerilatorSimulation
from .simulation_settings import SimulationSettings, SimulationSettingsDialog
from .toolchain import resolve_verilator
from .theme import application_palette, application_stylesheet, load_theme_mode
from .verilog_interface import VerilogInterface
from .update_controller import UpdateController
from .virtual_lab import FPGAVirtualLab


class BuildWorker(QThread):
    """Compile or recover one cached model without blocking the Qt event loop."""

    completed = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(
        self, cache_dir: Path | None, project: IcestudioProject, profile: BoardProfile,
        top_module: str, optimization_mode: str, parent=None,
    ):
        super().__init__(parent)
        self._cache_dir = cache_dir
        self._project = project
        self._profile = profile
        self._top_module = top_module
        self._optimization_mode = optimization_mode
        self._cancel_requested = Event()

    def cancel(self) -> None:
        """Request cancellation of the current compiler process tree."""
        self._cancel_requested.set()

    def run(self) -> None:
        try:
            artifact = VerilatorBuildCache(self._cache_dir).build_or_reuse(
                self._project,
                self._profile,
                top_module=self._top_module,
                optimization_mode=self._optimization_mode,
                cancel_requested=self._cancel_requested.is_set,
            )
        except BuildCancelled:
            return
        except Exception as error:
            self.failed.emit(str(error))
            return
        self.completed.emit(artifact)


@dataclass(frozen=True)
class PendingProjectRun:
    """UI data retained while the model is being built on a worker thread."""

    project: IcestudioProject
    profile: BoardProfile
    module_name: str
    led_sources: dict[int, tuple[str, int]]
    input_sources: dict[str, tuple[str, int]]
    board_id: str = DEFAULT_BOARD_ID


def migrate_legacy_clock(store: QSettings, window: FPGALabMainWindow) -> None:
    """Move the former global clock to the active Lab once."""
    if not store.contains(SimulationSettings.CLOCK_KEY):
        return
    try:
        legacy_hz = int(store.value(SimulationSettings.CLOCK_KEY))
    except (TypeError, ValueError):
        legacy_hz = 0
    try:
        current_override = window.lab_clock_override_hz()
    except (OSError, ValueError, json.JSONDecodeError):
        return
    if 1 <= legacy_hz <= 1_000_000_000 and current_override is None:
        window.save_selected_lab_clock_override(legacy_hz)
    store.remove(SimulationSettings.CLOCK_KEY)
    store.sync()


def parse_arguments() -> argparse.Namespace:
    """Parse command-line options while keeping the normal path GUI-first."""
    parser = argparse.ArgumentParser(description="Open the virtual FPGA lab.")
    parser.add_argument("--library", type=Path, help="Prebuilt library (advanced mode).")
    parser.add_argument("--ice", type=Path, help="Icestudio .ice file to open at startup.")
    parser.add_argument("--cache-dir", type=Path, help="Optional Verilator cache location.")
    parser.add_argument("--profile", type=Path, help="Manual profile (optional for Icestudio designs).")
    parser.add_argument("--clock-hz", type=int, help="Override the saved virtual clock frequency for this launch.")
    parser.add_argument("--ui-refresh-hz", type=int, help="Override the saved UI refresh frequency for this launch.")
    parser.add_argument("--observation-hz", type=int, help="Override the saved peripheral temporal sampling rate for this launch.")
    return parser.parse_args()


def project_clock_port(project: IcestudioProject, interface: VerilogInterface, board_id: str = DEFAULT_BOARD_ID) -> str | None:
    """Prefer the HDL net constrained to the board's physical clock endpoint."""
    if project.pcf is None:
        return None
    board = BoardDefinition.load(bundled_board_definition(board_id))
    pin_map = ProjectPinMap.from_pcf(board, project.pcf)
    inputs = {port.name: port.width for port in interface.ports if port.direction in {"input", "inout"}}
    reference = signal_reference(pin_map.net_for(board.clock_endpoint), inputs) if board.clock_endpoint else None
    return reference[0] if reference is not None and reference[1] == 0 and inputs[reference[0]] == 1 else None


def board_sources(project: IcestudioProject, profile: BoardProfile, board_id: str = DEFAULT_BOARD_ID) -> tuple[dict[int, tuple[str, int]], dict[str, tuple[str, int]]]:
    """Resolve physical board controls to the random HDL names recorded in the PCF."""
    if project.pcf is None:
        return {}, {}
    board = BoardDefinition.load(bundled_board_definition(board_id))
    pin_map = ProjectPinMap.from_pcf(board, project.pcf)
    led_sources = {
        index: reference
        for index, endpoint in enumerate(board.led_endpoints)
        if (reference := signal_reference(pin_map.net_for(endpoint), profile.outputs)) is not None
    }
    input_sources = {
        endpoint: reference
        for endpoint in board.input_endpoints
        if (reference := signal_reference(pin_map.net_for(endpoint), profile.inputs)) is not None
    }
    return led_sources, input_sources



class ApplicationController(QObject):
    """Compile selected designs and replace the hosted virtual laboratory."""

    def __init__(self, app: QApplication, window: FPGALabMainWindow, namespace: argparse.Namespace):
        super().__init__(app)
        self._app = app
        self._window = window
        self._namespace = namespace
        VerilatorBuildCache(namespace.cache_dir).maintain()
        self._board_id = window.selected_board_id()
        self._settings_store = window.user_settings()
        migrate_legacy_clock(self._settings_store, window)
        self._simulation_settings = SimulationSettings.load(
            self._settings_store, default_clock_hz=self._effective_clock_hz(self._board_id)
        ).with_overrides(
            ui_refresh_hz=namespace.ui_refresh_hz,
            observation_hz=namespace.observation_hz,
        )
        self._manual_profile = BoardProfile.load(namespace.profile) if namespace.profile else None
        self._build_worker: BuildWorker | None = None
        self._pending_run: PendingProjectRun | None = None
        self._switching_lab = False
        window.project_requested.connect(self.execute_project)
        window.board_selected.connect(self.select_board)
        window.lab_selected.connect(self.switch_lab)
        window.stop_requested.connect(self.stop_simulation)
        window.toolchain_requested.connect(self.check_toolchain)
        window.simulation_settings_requested.connect(self.configure_simulation)
        window.closing.connect(self.shutdown)
        app.aboutToQuit.connect(self.shutdown)
        window.set_clock_performance(self._simulation_settings.clock_hz)

    def _lab_clock_override_hz(self) -> int | None:
        try:
            return self._window.lab_clock_override_hz()
        except (OSError, ValueError, json.JSONDecodeError) as error:
            self._window.set_status(t("Invalid Lab clock; using the board clock: {error}", error=error))
            return None

    def _effective_clock_hz(self, board_id: str, *, use_lab_override: bool = True) -> int:
        if self._namespace.clock_hz is not None:
            return self._namespace.clock_hz
        override = self._lab_clock_override_hz() if use_lab_override else None
        return override if override is not None else self._window.board_clock_hz(board_id)

    @property
    def clock_hz(self) -> int:
        return self._simulation_settings.clock_hz

    def select_board(self, board_id: str) -> None:
        """Use the selected package for the visible board and the next build."""
        if board_id == self._board_id:
            return
        active_lab = self._window.active_lab()
        if active_lab is not None and not active_lab.close():
            self._window.select_board(self._board_id)
            self._window.set_status(t("Could not stop the previous simulation safely."))
            return
        try:
            clock_hz = self._effective_clock_hz(board_id, use_lab_override=self._switching_lab)
            lab = FPGAVirtualLab(
                clock_hz=clock_hz, lab_file=self._window.selected_lab(), board_id=board_id
            )
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
            self._window.select_board(self._board_id)
            QMessageBox.warning(self._window, t("Cannot load lab"), str(error))
            return
        self._board_id = board_id
        self._simulation_settings = self._simulation_settings.with_overrides(clock_hz=clock_hz)
        self._window.set_lab(lab)
        if not self._switching_lab:
            self._window.save_selected_lab_board(board_id)
        self._window.set_clock_performance(self._simulation_settings.clock_hz)
        self._window.set_status(t("Board selected: {name}", name=self._window.board_name(board_id)))

    def switch_lab(self, lab_file: Path) -> None:
        """Apply the selected laboratory to the visible workbench immediately."""
        active_lab = self._window.active_lab()
        board_id = self._window.board_id_for_lab(lab_file)
        if board_id != self._board_id:
            previous_lab_file = active_lab._lab_file if isinstance(active_lab, FPGAVirtualLab) else None
            self._switching_lab = True
            try:
                self._window.select_board(board_id)
            finally:
                self._switching_lab = False
            if self._board_id != board_id and previous_lab_file is not None:
                self._window.select_lab(previous_lab_file)
            return
        if not isinstance(active_lab, FPGAVirtualLab):
            return
        self._simulation_settings = self._simulation_settings.with_overrides(
            clock_hz=self._effective_clock_hz(board_id)
        )
        try:
            active_lab.set_lab_file(lab_file)
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
            QMessageBox.warning(self._window, t("Cannot load lab"), str(error))
            return
        self._window.set_clock_performance(self._simulation_settings.clock_hz)
        self._window.set_status(t("Lab loaded: {name}", name=lab_file.stem.removesuffix(".lab")))

    def execute_project(self, ice_file: Path) -> None:
        if self._build_worker is not None:
            self._window.set_status(t("A build is already in progress."))
            return
        try:
            project = IcestudioProject.discover(ice_file)
            interface = VerilogInterface.discover(project.main_v)
            clock_port = project_clock_port(project, interface, self._board_id)
            board_name = self._window.board_name(self._board_id)
            profile = self._manual_profile or interface.profile(
                board_name=board_name, clock_port=clock_port
            )
            led_sources, input_sources = board_sources(project, profile, self._board_id)
            if self._manual_profile is None:
                profile = apply_led_observed(profile, led_sources)
        except (IcestudioProjectError, ValueError, OSError) as error:
            QMessageBox.critical(self._window, t("Cannot load design"), str(error))
            return

        self._window.set_status(
            t("Preparing {name}: analyzing HDL and looking for a cached build…", name=project.ice_file.name)
        )
        self._window.show_busy(t(
            "Preparing {name}. FPGALab is checking the cache and may compile the HDL model.",
            name=project.ice_file.name,
        ))
        self._pending_run = PendingProjectRun(project, profile, interface.module_name, led_sources, input_sources, self._board_id)
        self._window.set_project_loading(True)
        # The worker must outlive the window while a native build is running.
        self._build_worker = BuildWorker(
            self._namespace.cache_dir, project, profile, interface.module_name,
            self._simulation_settings.verilator_optimization,
        )
        self._build_worker.completed.connect(self._complete_build)
        self._build_worker.failed.connect(self._build_failed)
        self._build_worker.finished.connect(self._dispose_build_worker)
        self._build_worker.start()

    def _complete_build(self, artifact) -> None:
        pending = self._pending_run
        if pending is None:
            return
        previous_lab = self._window.active_lab()
        workbench_history = (
            previous_lab.workbench_history()
            if isinstance(previous_lab, FPGAVirtualLab) and getattr(previous_lab, "_board_id", pending.board_id) == pending.board_id else None
        )
        # Cached builds can load the same shared library again. Its model and
        # UART channel state are process-global, so the old worker must finish
        # and close that model before the next VerilatorSimulation calls init_sim().
        if previous_lab is not None and not previous_lab.close():
            self._build_failed(t("Could not stop the previous simulation safely."))
            return
        try:
            simulation = VerilatorSimulation(artifact.library, pending.profile)
        except Exception as error:
            self._build_failed(str(error))
            return
        self._window.dismiss_busy()
        lab = FPGAVirtualLab(
            simulation,
            self._simulation_settings.clock_hz,
            self._simulation_settings.ui_refresh_hz,
            self._simulation_settings.observation_hz,
            project_pcf=pending.project.pcf,
            lab_file=self._window.selected_lab(),
            board_id=pending.board_id,
            led_sources=pending.led_sources,
            input_sources=pending.input_sources,
        )
        if workbench_history is not None:
            lab.restore_workbench_history(workbench_history)
        self._window.set_lab(lab)
        lab.status_changed.connect(self._window.set_status)
        lab.clock_performance_changed.connect(self._window.set_clock_performance)
        self._window.set_clock_performance(
            self._simulation_settings.clock_hz if pending.profile.clock_name is not None else None
        )
        lab.start_simulation()
        self._window.set_simulation_running(True)
        self._window.set_project_path(pending.project.ice_file)
        self._window.remember_project(pending.project.ice_file)
        source = t("cache") if artifact.reused else t("incremental build") if artifact.incremental else t("new build")
        compatibility = t("compatibility optimization enabled") if artifact.compatibility_mode else t("standard optimization")
        run_state = t("simulation started") if pending.profile.clock_name is not None else t("combinational logic active")
        self._window.set_status(t(
            "{name}: {state} ({source}, module {module}, {optimization}).",
            name=pending.project.ice_file.name,
            state=run_state,
            source=source,
            module=pending.module_name,
            optimization=compatibility,
        ))
        self._pending_run = None

    def _build_failed(self, error: str) -> None:
        self._window.dismiss_busy()
        self._window.set_simulation_running(False)
        QMessageBox.critical(self._window, t("Build error"), error)
        self._window.set_status(t("Build did not complete."))
        self._pending_run = None

    def _dispose_build_worker(self) -> None:
        worker = self._build_worker
        self._build_worker = None
        if worker is not None:
            worker.deleteLater()

    def shutdown(self) -> None:
        """Cancel an in-flight native build before Qt destroys thread objects."""
        worker = self._build_worker
        if worker is not None and worker.isRunning():
            worker.cancel()
            if not worker.wait(5000):
                self._window.block_close(t("Waiting for the active build to stop safely."))

    def stop_simulation(self) -> None:
        """Stop the active clock without unloading the selected project."""
        active_lab = self._window.active_lab()
        if isinstance(active_lab, FPGAVirtualLab):
            active_lab.stop_simulation()
        self._window.set_simulation_running(False)
        active_lab = self._window.active_lab()
        if isinstance(active_lab, FPGAVirtualLab):
            self._window.set_clock_performance(active_lab.requested_clock_hz())
        self._window.set_status(t("Simulation stopped."))

    def check_toolchain(self) -> None:
        """Report the resolved compiler stack before a user starts a build."""
        try:
            toolchain = resolve_verilator()
            toolchain.validate_build_prerequisites()
        except Exception as error:
            self._window.set_status(t("Simulation toolchain is not ready."))
            QMessageBox.warning(self._window, t("Simulation toolchain"), str(error))
            return
        details = [
            t("Ready to compile."),
            "",
            t("Source: {source}", source=toolchain.source),
        ]
        if toolchain.suite_root is not None:
            details.append(t("Toolchain root: {path}", path=toolchain.suite_root))
        details.append(t("Verilator: {path}", path=toolchain.executable))
        for name, path in toolchain.build_tools().items():
            details.append(t("{tool}: {path}", tool=name, path=path))
        cache = VerilatorBuildCache(self._namespace.cache_dir)
        details.append(t(
            "Build cache: {used} of {limit} (managed automatically)",
            used=_format_storage(cache.usage_bytes()),
            limit=_format_storage(cache.budget_bytes()),
        ))
        message = "\n".join(details)
        self._window.set_status(t("Simulation toolchain is ready."))
        QMessageBox.information(self._window, t("Simulation toolchain"), message)

    def configure_simulation(self) -> None:
        """Persist runtime rates selected in the graphical interface."""
        dialog = SimulationSettingsDialog(
            self._simulation_settings,
            self._window.board_clock_hz(self._board_id),
            self._lab_clock_override_hz(),
            self._window,
        )
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        self._window.save_selected_lab_clock_override(dialog.clock_override_hz())
        self._simulation_settings = dialog.values().with_overrides(clock_hz=self._effective_clock_hz(self._board_id))
        self._simulation_settings.save(self._settings_store)
        self._window.set_clock_performance(self._simulation_settings.clock_hz)
        self._window.set_status(t("Simulation settings saved. They will apply on the next run."))

    def load_advanced_library(self, library: Path) -> None:
        profile = self._manual_profile or BoardProfile.load(bundled_profile(self._board_id))
        try:
            simulation = VerilatorSimulation(library, profile)
        except Exception as error:
            QMessageBox.critical(self._window, t("Cannot open library"), str(error))
            return
        self._window.set_lab(FPGAVirtualLab(
            simulation,
            self._simulation_settings.clock_hz,
            self._simulation_settings.ui_refresh_hz,
            self._simulation_settings.observation_hz,
            board_id=self._board_id,
            lab_file=self._window.selected_lab(),
        ))
        self._window.set_clock_performance(
            self._simulation_settings.clock_hz if profile.clock_name is not None else None
        )
        self._window.set_simulation_running(False)
        self._window.set_status(t("Advanced library loaded. Select an .ice file to change design."))


def _format_storage(size: int) -> str:
    """Format cache sizes compactly for the toolchain diagnostic."""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024.0 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} GB"


def main() -> None:
    namespace = parse_arguments()
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("FPGALab.FPGALab")
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setApplicationName("FPGALab")
    app.setApplicationDisplayName("FPGALab")
    app.setOrganizationName("FPGALab")
    qt_dialog_translations = QtDialogTranslations(app)
    theme_mode = load_theme_mode()
    app.setPalette(application_palette(theme_mode))
    app.setStyleSheet(application_stylesheet(theme_mode))
    if hasattr(app, "setDesktopFileName"):
        app.setDesktopFileName("fpgalab")
    app.setWindowIcon(application_icon())
    workspace = LabWorkspace()
    window = FPGALabMainWindow(workspace)
    window.setWindowIcon(application_icon())
    controller = ApplicationController(app, window, namespace)
    window.set_lab(FPGAVirtualLab(
        clock_hz=controller.clock_hz,
        lab_file=window.selected_lab(), board_id=window.selected_board_id(),
    ))
    update_controller = UpdateController(window)
    window.update_requested.connect(update_controller.check_manually)
    QTimer.singleShot(1200, update_controller.check_on_startup)
    if namespace.ice:
        window.set_project_path(namespace.ice)
    window.showMaximized()
    QTimer.singleShot(100, window.showMaximized)
    if namespace.ice:
        QTimer.singleShot(0, lambda: controller.execute_project(namespace.ice))
    elif namespace.library:
        QTimer.singleShot(0, lambda: controller.load_advanced_library(namespace.library))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
