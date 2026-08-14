"""Punto de entrada de la GUI independiente de AlhambraLab."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from .compiler import shared_library_name
from .profile import BoardProfile
from .simulation import VerilatorSimulation
from .virtual_lab import AlhambraVirtualLab


def main() -> None:
    parser = argparse.ArgumentParser(description="Abre el laboratorio virtual Alhambra II.")
    parser.add_argument("--library", type=Path, default=Path("build/verilator/obj_dir") / shared_library_name())
    parser.add_argument("--profile", type=Path, default=Path("examples/board_profile.json"))
    parser.add_argument("--ticks-per-frame", type=int, default=12_000)
    ns = parser.parse_args()
    app = QApplication(sys.argv)
    simulation = VerilatorSimulation(ns.library, BoardProfile.load(ns.profile))
    window = AlhambraVirtualLab(simulation, ns.ticks_per_frame)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
