"""Standalone FPGALab GUI entry point."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import QApplication, QMessageBox

from .board import BoardDefinition, bundled_board_definition
from .branding import application_icon
from .build_cache import VerilatorBuildCache
from .ice_project import IcestudioProject, IcestudioProjectError
from .i18n import t
from .lab_workspace import LabWorkspace
from .main_window import FPGALabMainWindow
from .profile import BoardProfile, bundled_profile
from .profile_policy import apply_led_observed
from .project_pins import ProjectPinMap
from .signals import signal_reference
from .simulation import VerilatorSimulation
from .toolchain import resolve_verilator
from .verilog_interface import VerilogInterface
from .update_controller import UpdateController
from .virtual_lab import FPGAVirtualLab


class BuildWorker(QThread):
    """Compile or recover one cached model without blocking the Qt event loop."""

    completed = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, cache_dir: Path | None, project: IcestudioProject, profile: BoardProfile, top_module: str, parent=None):
        super().__init__(parent)
        self._cache_dir = cache_dir
        self._project = project
        self._profile = profile
        self._top_module = top_module

    def run(self) -> None:
        try:
            artifact = VerilatorBuildCache(self._cache_dir).build_or_reuse(
                self._project,
                self._profile,
                top_module=self._top_module,
            )
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


def parse_arguments() -> argparse.Namespace:
    """Parse command-line options while keeping the normal path GUI-first."""
    parser = argparse.ArgumentParser(description="Open the virtual FPGA lab.")
    parser.add_argument("--library", type=Path, help="Prebuilt library (advanced mode).")
    parser.add_argument("--ice", type=Path, help="Icestudio .ice file to open at startup.")
    parser.add_argument("--cache-dir", type=Path, help="Optional Verilator cache location.")
    parser.add_argument("--profile", type=Path, help="Manual profile (optional for Icestudio designs).")
    parser.add_argument("--clock-hz", type=int, default=12_000_000, help="Target virtual clock frequency.")
    parser.add_argument("--ui-refresh-hz", type=int, default=60, help="Maximum UI refresh frequency.")
    parser.add_argument("--observation-hz", type=int, default=1_000_000, help="Peripheral temporal sampling rate.")
    return parser.parse_args()


def project_clock_port(project: IcestudioProject, interface: VerilogInterface) -> str | None:
    """Prefer the HDL net constrained to the board's physical clock endpoint."""
    if project.pcf is None:
        return None
    board = BoardDefinition.load(bundled_board_definition())
    pin_map = ProjectPinMap.from_pcf(board, project.pcf)
    inputs = {port.name: port.width for port in interface.ports if port.direction in {"input", "inout"}}
    reference = signal_reference(pin_map.net_for("CLK"), inputs)
    return reference[0] if reference is not None and reference[1] == 0 and inputs[reference[0]] == 1 else None


def board_sources(project: IcestudioProject, profile: BoardProfile) -> tuple[dict[int, tuple[str, int]], dict[str, tuple[str, int]]]:
    """Resolve physical board controls to the random HDL names recorded in the PCF."""
    if project.pcf is None:
        return {}, {}
    board = BoardDefinition.load(bundled_board_definition())
    pin_map = ProjectPinMap.from_pcf(board, project.pcf)
    led_sources = {
        index: reference
        for index in range(8)
        if (reference := signal_reference(pin_map.net_for(f"LED{index}"), profile.outputs)) is not None
    }
    input_sources = {
        endpoint: reference
        for endpoint in ("SW1", "SW2")
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
        self._manual_profile = BoardProfile.load(namespace.profile) if namespace.profile else None
        self._build_worker: BuildWorker | None = None
        self._pending_run: PendingProjectRun | None = None
        window.project_requested.connect(self.execute_project)
        window.lab_selected.connect(self.switch_lab)
        window.stop_requested.connect(self.stop_simulation)
        window.toolchain_requested.connect(self.check_toolchain)
        app.aboutToQuit.connect(self.shutdown)

    def switch_lab(self, lab_file: Path) -> None:
        """Apply the selected laboratory to the visible workbench immediately."""
        active_lab = self._window.active_lab()
        if not isinstance(active_lab, FPGAVirtualLab):
            return
        try:
            active_lab.set_lab_file(lab_file)
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
            QMessageBox.warning(self._window, t("Cannot load lab"), str(error))
            return
        self._window.set_status(t("Lab loaded: {name}", name=lab_file.stem.removesuffix(".lab")))

    def execute_project(self, ice_file: Path) -> None:
        if self._build_worker is not None:
            self._window.set_status(t("A build is already in progress."))
            return
        try:
            project = IcestudioProject.discover(ice_file)
            interface = VerilogInterface.discover(project.main_v)
            clock_port = project_clock_port(project, interface)
            profile = self._manual_profile or interface.profile(clock_port=clock_port)
            led_sources, input_sources = board_sources(project, profile)
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
        self._pending_run = PendingProjectRun(project, profile, interface.module_name, led_sources, input_sources)
        self._window.set_project_loading(True)
        # The worker must outlive the window while a native build is running.
        self._build_worker = BuildWorker(self._namespace.cache_dir, project, profile, interface.module_name)
        self._build_worker.completed.connect(self._complete_build)
        self._build_worker.failed.connect(self._build_failed)
        self._build_worker.finished.connect(self._dispose_build_worker)
        self._build_worker.start()

    def _complete_build(self, artifact) -> None:
        pending = self._pending_run
        if pending is None:
            return
        try:
            simulation = VerilatorSimulation(artifact.library, pending.profile)
        except Exception as error:
            self._build_failed(str(error))
            return
        active_lab = self._window.active_lab()
        previous_zoom = active_lab.workbench_zoom() if isinstance(active_lab, FPGAVirtualLab) else 1.0
        self._window.dismiss_busy()
        lab = FPGAVirtualLab(
            simulation,
            self._namespace.clock_hz,
            self._namespace.ui_refresh_hz,
            self._namespace.observation_hz,
            project_pcf=pending.project.pcf,
            lab_file=self._window.selected_lab(),
            led_sources=pending.led_sources,
            input_sources=pending.input_sources,
        )
        lab.set_workbench_zoom(previous_zoom)
        self._window.set_lab(lab)
        lab.status_changed.connect(self._window.set_status)
        lab.start_simulation()
        self._window.set_simulation_running(True)
        self._window.set_project_path(pending.project.ice_file)
        self._window.remember_project(pending.project.ice_file)
        source = t("cache") if artifact.reused else t("new build")
        run_state = t("simulation started") if pending.profile.clock_name is not None else t("combinational logic active")
        self._window.set_status(t("{name}: {state} ({source}, module {module}).", name=pending.project.ice_file.name, state=run_state, source=source, module=pending.module_name))
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
        """Wait for an in-flight native build before Qt destroys thread objects."""
        worker = self._build_worker
        if worker is not None and worker.isRunning():
            worker.wait()

    def stop_simulation(self) -> None:
        """Stop the active clock without unloading the selected project."""
        active_lab = self._window.active_lab()
        if isinstance(active_lab, FPGAVirtualLab):
            active_lab.stop_simulation()
        self._window.set_simulation_running(False)
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
        message = t(
            "Ready to compile.\n\nSource: {source}\nVerilator: {path}",
            source=toolchain.source,
            path=toolchain.executable,
        )
        self._window.set_status(t("Simulation toolchain is ready."))
        QMessageBox.information(self._window, t("Simulation toolchain"), message)

    def load_advanced_library(self, library: Path) -> None:
        profile = self._manual_profile or BoardProfile.load(bundled_profile())
        try:
            simulation = VerilatorSimulation(library, profile)
        except Exception as error:
            QMessageBox.critical(self._window, t("Cannot open library"), str(error))
            return
        self._window.set_lab(FPGAVirtualLab(
            simulation,
            self._namespace.clock_hz,
            self._namespace.ui_refresh_hz,
            self._namespace.observation_hz,
        ))
        self._window.set_simulation_running(False)
        self._window.set_status(t("Advanced library loaded. Select an .ice file to change design."))


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
    if hasattr(app, "setDesktopFileName"):
        app.setDesktopFileName("fpgalab")
    app.setWindowIcon(application_icon())
    workspace = LabWorkspace()
    window = FPGALabMainWindow(workspace)
    window.setWindowIcon(application_icon())
    window.set_lab(FPGAVirtualLab(lab_file=window.selected_lab()))
    controller = ApplicationController(app, window, namespace)
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
