"""Punto de entrada de la GUI independiente de FPGALab."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QApplication

from .compiler import shared_library_name
from .profile import BoardProfile
from .simulation import VerilatorSimulation
from .virtual_lab import FPGAVirtualLab


def main() -> None:
    parser = argparse.ArgumentParser(description="Abre el laboratorio virtual FPGA.")
    parser.add_argument("--library", type=Path, default=Path("build/verilator/obj_dir") / shared_library_name())
    parser.add_argument("--profile", type=Path, default=Path("examples/board_profile.json"))
    parser.add_argument("--clock-hz", type=int, default=12_000_000, help="Frecuencia virtual objetivo.")
    parser.add_argument("--ui-refresh-hz", type=int, default=60, help="Frecuencia máxima de pintado.")
    parser.add_argument("--observation-hz", type=int, default=1_000_000, help="Muestreo temporal para periféricos.")
    ns = parser.parse_args()
    app = QApplication(sys.argv)
    simulation = VerilatorSimulation(ns.library, BoardProfile.load(ns.profile))
    window = FPGAVirtualLab(simulation, ns.clock_hz, ns.ui_refresh_hz, ns.observation_hz)
    window.setWindowState(Qt.WindowState.WindowMaximized)
    window.show()
    QTimer.singleShot(100, window.showMaximized)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
