"""Standalone FPGALab GUI entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QApplication, QMessageBox, QProgressDialog

from .build_cache import VerilatorBuildCache
from .ice_project import IcestudioProject, IcestudioProjectError
from .profile import BoardProfile
from .project_launcher import ProjectLauncherDialog
from .recent_projects import RecentProjects
from .simulation import VerilatorSimulation
from .virtual_lab import FPGAVirtualLab


def parse_arguments() -> argparse.Namespace:
    """Parse command-line options while keeping the normal path GUI-first."""
    parser = argparse.ArgumentParser(description="Abre el laboratorio virtual FPGA.")
    parser.add_argument("--library", type=Path, default=None, help="Biblioteca ya compilada (modo avanzado).")
    parser.add_argument("--ice", type=Path, help="Archivo .ice cuyo ice-build se ejecutará.")
    parser.add_argument("--cache-dir", type=Path, help="Ubicación opcional de cache Verilator.")
    parser.add_argument("--profile", type=Path, default=Path("examples/board_profile.json"))
    parser.add_argument("--clock-hz", type=int, default=12_000_000, help="Frecuencia virtual objetivo.")
    parser.add_argument("--ui-refresh-hz", type=int, default=60, help="Frecuencia máxima de pintado.")
    parser.add_argument("--observation-hz", type=int, default=1_000_000, help="Muestreo temporal para periféricos.")
    return parser.parse_args()


def select_project(app: QApplication, requested_file: Path | None) -> IcestudioProject | None:
    """Return a discovered project from the CLI or the interactive picker."""
    recent_projects = RecentProjects()
    if requested_file is None:
        dialog = ProjectLauncherDialog(recent_projects)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return None
        requested_file = dialog.selected_file
    try:
        project = IcestudioProject.discover(requested_file)
    except IcestudioProjectError as error:
        QMessageBox.critical(None, "No se puede ejecutar", str(error))
        return None
    recent_projects.add(project.ice_file)
    return project


def build_project(
    app: QApplication, project: IcestudioProject, profile: BoardProfile, cache_dir: Path | None
) -> Path | None:
    """Build or reuse a cached shared library while showing a visible status dialog."""
    progress = QProgressDialog("Buscando compilación compatible…", None, 0, 0)
    progress.setWindowTitle("FPGALab")
    progress.setCancelButton(None)
    progress.setMinimumDuration(0)
    progress.setWindowModality(Qt.WindowModality.ApplicationModal)
    progress.show()
    app.processEvents()
    try:
        artifact = VerilatorBuildCache(cache_dir).build_or_reuse(project, profile)
    except Exception as error:
        QMessageBox.critical(None, "Error de compilación", str(error))
        return None
    finally:
        progress.close()
    print(f"{'cache hit' if artifact.reused else 'compiled'}: {artifact.library}")
    return artifact.library


def main() -> None:
    namespace = parse_arguments()
    app = QApplication(sys.argv)
    profile = BoardProfile.load(namespace.profile)
    project: IcestudioProject | None = None
    if namespace.ice or not namespace.library:
        project = select_project(app, namespace.ice)
        if project is None:
            return
        library = build_project(app, project, profile, namespace.cache_dir)
        if library is None:
            return
        project_pcf = project.pcf
        lab_file = project.ensure_lab_file()
    else:
        library = namespace.library
        project_pcf = Path("examples/main.pcf")
        lab_file = Path("examples/lab.json")

    simulation = VerilatorSimulation(library, profile)
    window = FPGAVirtualLab(
        simulation,
        namespace.clock_hz,
        namespace.ui_refresh_hz,
        namespace.observation_hz,
        project_pcf=project_pcf,
        lab_file=lab_file,
    )
    window.setWindowState(Qt.WindowState.WindowMaximized)
    window.show()
    QTimer.singleShot(100, window.showMaximized)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
