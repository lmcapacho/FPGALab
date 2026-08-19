"""Standalone FPGALab GUI entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QApplication, QMessageBox, QProgressDialog

from .build_cache import VerilatorBuildCache
from .ice_project import IcestudioProject, IcestudioProjectError
from .main_window import FPGALabMainWindow
from .profile import BoardProfile
from .simulation import VerilatorSimulation
from .verilog_interface import VerilogInterface
from .virtual_lab import FPGAVirtualLab


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


class ApplicationController:
    """Compile selected designs and replace the hosted virtual laboratory."""

    def __init__(self, app: QApplication, window: FPGALabMainWindow, namespace: argparse.Namespace):
        self._app = app
        self._window = window
        self._namespace = namespace
        self._manual_profile = BoardProfile.load(namespace.profile) if namespace.profile else None
        window.project_requested.connect(self.execute_project)

    def execute_project(self, ice_file: Path) -> None:
        try:
            project = IcestudioProject.discover(ice_file)
            interface = VerilogInterface.discover(project.main_v)
            profile = self._manual_profile or interface.profile()
        except (IcestudioProjectError, ValueError) as error:
            QMessageBox.critical(self._window, "No se puede ejecutar", str(error))
            return

        self._window.set_status(f"Preparando {project.ice_file.name}…")
        progress_parent = self._window if self._window.isVisible() else None
        progress = QProgressDialog("Preparando simulación…", None, 0, 0, progress_parent)
        progress.setWindowTitle("FPGALab · Cargando diseño")
        progress.setLabelText("Analizando HDL y buscando una compilación en caché…")
        progress.setCancelButton(None)
        progress.setMinimumDuration(0)
        progress.setMinimumWidth(460)
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.show()
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
        finally:
            progress.close()

        lab = FPGAVirtualLab(
            simulation,
            self._namespace.clock_hz,
            self._namespace.ui_refresh_hz,
            self._namespace.observation_hz,
            project_pcf=project.pcf,
            lab_file=project.ensure_lab_file(),
        )
        self._window.set_lab(lab)
        self._window.set_project_path(project.ice_file)
        self._window.remember_project(project.ice_file)
        source = "caché" if artifact.reused else "compilación nueva"
        self._window.set_status(f"{project.ice_file.name} listo ({source}, módulo {interface.module_name}).")

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
        self._window.set_status("Biblioteca avanzada cargada. Seleccione un .ice para cambiar de diseño.")


def main() -> None:
    namespace = parse_arguments()
    app = QApplication(sys.argv)
    window = FPGALabMainWindow()
    controller = ApplicationController(app, window, namespace)
    if namespace.ice:
        window.set_project_path(namespace.ice)
        controller.execute_project(namespace.ice)
    window.showMaximized()
    if namespace.library:
        QTimer.singleShot(0, lambda: controller.load_advanced_library(namespace.library))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
