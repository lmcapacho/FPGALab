"""Medición reproducible de motor Verilator con capas de placa y cableado."""

from __future__ import annotations

import argparse
from time import perf_counter
from pathlib import Path

from .board import BoardDefinition
from .constraints import PcfParser
from .profile import BoardProfile
from .simulation import VerilatorSimulation
from .wiring import VirtualLabProject


def main() -> None:
    parser = argparse.ArgumentParser(description="Mide la tasa efectiva de FPGALab.")
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--board", type=Path, required=True)
    parser.add_argument("--pcf", type=Path, required=True)
    parser.add_argument("--lab", type=Path, required=True)
    parser.add_argument("--seconds", type=int, default=1)
    parser.add_argument("--ui-fps", type=int, default=60)
    ns = parser.parse_args()
    board = BoardDefinition.load(ns.board)
    constraints = PcfParser.parse_file(ns.pcf)
    project = VirtualLabProject.load(ns.lab)
    setup_started = perf_counter()
    wires = project.resolve(board, constraints)
    setup_elapsed = perf_counter() - setup_started
    profile = BoardProfile.load(ns.profile)
    simulation = VerilatorSimulation(ns.library, profile)
    frames = ns.seconds * ns.ui_fps
    total_cycles = board.clock_hz * ns.seconds
    base_cycles, extra_cycles = divmod(total_cycles, frames)
    started = perf_counter()
    checksum = 0
    for frame in range(frames):
        simulation.ticks(base_cycles + (1 if frame < extra_cycles else 0))
        checksum += sum(simulation.read_leds())
        checksum += simulation.get_output("segments") if "segments" in profile.outputs else 0
        checksum += simulation.get_output("gpio_out") if "gpio_out" in profile.outputs else 0
    elapsed = perf_counter() - started
    simulation.close()
    rate_mhz = total_cycles / elapsed / 1_000_000
    print(f"wires={len(wires)} setup_ms={setup_elapsed * 1_000:.3f}")
    print(f"virtual_cycles={total_cycles} ui_frames={frames} rate_mhz={rate_mhz:.2f} checksum={checksum}")


if __name__ == "__main__":
    main()
