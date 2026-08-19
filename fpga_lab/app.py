"""Standalone FPGALab GUI entry point."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QMessageBox

from .board import BoardDefinition
from .build_cache import VerilatorBuildCache
from .ice_project import IcestudioProject, IcestudioProjectError
from .main_window import FPGALabMainWindow
from .profile import BoardProfile
from .project_pins import ProjectPinMap
from .simulation import VerilatorSimulation
from .verilog_interface import VerilogInterface
from .virtual_lab import FPGAVirtualLab

_SIGNAL_REFERENCE = re.compile(r"([A-Za-z_][A-Za-z0-9_$]*)(?:\[(\d+)])?$")


def parse_arguments() -> argparse.Namespace:
    """Parse command-line options while keeping the normal path GUI-first."""
    parser = argparse.ArgumentParser(description="Abre el laboratorio virtual FPGA.")
    parser.add_argument("--library", type=Path, help="Biblioteca ya compilada (modo avanzado).")
    parser.add_argument("--ice", type=Path, help="Archivo .ice que se abrirá al iniciar.")
    parser.add_argument("--cache-dir", type=Path, help="Ubicación opcional de cache Verilator.")
    parser.add_argument("--profile", type=Path, help="Perfil manual (opcional para diseños Icestudio).")
    parser.add_argument("--clock-hz", type=int, default=12_000_000, help="Frecuencia virtual objetivo.")
    parser.add_argument("--ui-refresh-hz", type=int, default=60, help="Frecuencia máxima de pintado.")
    parser.add_argument("--observation-hz", type=int, default=1_000_000, help="Muestreo temporal para periféricos.")
    return parser.parse_args()


def signal_reference(net: str | None, ports: dict[str, int]) -> tuple[str, int] | None:
    """Convert a PCF net such as ``vinit[2]`` into an ABI port and bit."""
    match = _SIGNAL_REFERENCE.fullmatch(net or "")
    if match is None:
        return None
    name, raw_bit = match.groups()
    bit = int(raw_bit) if raw_bit else 0
    if name not in ports or bit >= ports[name]:
        return None
    return name, bit


def project_clock_port(project: IcestudioProject, interface: VerilogInterface) -> str | None:
    """Prefer the HDL net constrained to the board's physical clock endpoint."""
    if project.pcf is None:
        return None
    board = BoardDefinition.load(Path("boards/alhambra_ii.json"))
    pin_map = ProjectPinMap.from_pcf(board, project.pcf)
    inputs = {port.name: port.width for port in interface.ports if port.direction in {"input", "inout"}}
    reference = signal_reference(pin_map.net_for("CLK"), inputs)
    return reference[0] if reference is not None and reference[1] == 0 and inputs[reference[0]] == 1 else None


def board_sources(project: IcestudioProject, profile: BoardProfile) -> tuple[dict[int, tuple[str, int]], dict[str, tuple[str, int]]]:
    """Resolve physical board controls to the random HDL names recorded in the PCF."""
    if project.pcf is None:
        return {}, {}
    board = BoardDefinition.load(Path("boards/alhambra_ii.json"))
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



class ApplicationController:
    """Compile selected designs and replace the hosted virtual laboratory."""

    def __init__(self, app: QApplication, window: FPGALabMainWindow, namespace: argparse.Namespace):
        self._app = app
        self._window = window
        self._namespace = namespace
        self._manual_profile = BoardProfile.load(namespace.profile) if namespace.profile else None
        window.project_requested.connect(self.execute_project)
        window.stop_requested.connect(self.stop_simulation)

    def execute_project(self, ice_file: Path) -> None:
        try:
            project = IcestudioProject.discover(ice_file)
            interface = VerilogInterface.discover(project.main_v)
            clock_port = project_clock_port(project, interface)
            profile = self._manual_profile or interface.profile(clock_port=clock_port)
            led_sources, input_sources = board_sources(project, profile)
        except (IcestudioProjectError, ValueError) as error:
            QMessageBox.critical(self._window, "No se puede cargar el diseño", str(error))
            return

        self._window.set_status(
            f"Preparando {project.ice_file.name}: analizando HDL y buscando compilación en caché…"
        )
        self._app.processEvents()
        try:
            artifact = VerilatorBuildCache(self._namespace.cache_dir).build_or_reuse(
                project, profile, top_module=interface.module_name
            )
            simulation = VerilatorSimulation(artifact.library, profile)
        except Exception as error:
            QMessageBox.critical(self._window, "Error de compilación", str(error))
            self._window.set_status("La compilación no terminó.")
            return
        lab = FPGAVirtualLab(
            simulation,
            self._namespace.clock_hz,
            self._namespace.ui_refresh_hz,
            self._namespace.observation_hz,
            project_pcf=project.pcf,
            lab_file=project.ensure_lab_file(),
            led_sources=led_sources,
            input_sources=input_sources,
        )
        self._window.set_lab(lab)
        lab.start_simulation()
        self._window.set_simulation_running(profile.clock_name is not None)
        self._window.set_project_path(project.ice_file)
        self._window.remember_project(project.ice_file)
        source = "caché" if artifact.reused else "compilación nueva"
        run_state = "simulación iniciada" if profile.clock_name is not None else "lógica combinacional lista"
        self._window.set_status(f"{project.ice_file.name}: {run_state} ({source}, módulo {interface.module_name}).")

    def stop_simulation(self) -> None:
        """Stop the active clock without unloading the selected project."""
        active_lab = self._window.active_lab()
        if isinstance(active_lab, FPGAVirtualLab):
            active_lab.stop_simulation()
        self._window.set_simulation_running(False)
        self._window.set_status("Simulación detenida.")

    def load_advanced_library(self, library: Path) -> None:
        profile = self._manual_profile or BoardProfile.load(Path("examples/board_profile.json"))
        try:
            simulation = VerilatorSimulation(library, profile)
        except Exception as error:
            QMessageBox.critical(self._window, "No se puede abrir la biblioteca", str(error))
            return
        self._window.set_lab(FPGAVirtualLab(
            simulation,
            self._namespace.clock_hz,
            self._namespace.ui_refresh_hz,
            self._namespace.observation_hz,
        ))
        self._window.set_simulation_running(False)
        self._window.set_status("Biblioteca avanzada cargada. Seleccione un .ice para cambiar de diseño.")


def main() -> None:
    namespace = parse_arguments()
    app = QApplication(sys.argv)
    window = FPGALabMainWindow()
    window.set_lab(FPGAVirtualLab())
    controller = ApplicationController(app, window, namespace)
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
