"""Reactive MISO response through the generated native ABI."""
import shutil
import subprocess
from pathlib import Path

import pytest

from fpga_lab.cpp_wrapper import render_cpp_wrapper
from fpga_lab.profile import BoardProfile
from fpga_lab.simulation import VerilatorSimulation
from fpga_lab.spi_edges import spi_response_byte


@pytest.fixture
def spi_library(tmp_path):
    if shutil.which("g++") is None:
        pytest.skip("A C++ compiler is required for the SPI native harness")
    profile = BoardProfile("test", {"clk": 1, "controls": 2, "input_bus": 2},
                           {"sck": 1, "cs": 1, "echo": 2}, {}, "clk")
    (tmp_path / "wrapper.cpp").write_text(render_cpp_wrapper(profile))
    (tmp_path / "verilated.h").write_text("#pragma once\n#include <cstdint>\nclass VerilatedContext { public: void timeInc(uint64_t) {} };\n")
    (tmp_path / "Vtop.h").write_text(
        '#pragma once\n#include "verilated.h"\n'
        'class Vtop { public: uint8_t clk=0, controls=2, input_bus=0, sck=0, cs=1, echo=0; '
        'explicit Vtop(VerilatedContext*) {} void final() {} '
        'void eval() { sck=controls&1; cs=(controls>>1)&1; echo=input_bus; } };\n')
    native = Path(__file__).parents[1] / "fpga_lab/native"
    library = tmp_path / "spi.so"
    subprocess.run(["g++", "-std=c++17", "-shared", "-fPIC", "-O2", "-I", str(tmp_path), "-I", str(native),
                    str(tmp_path / "wrapper.cpp"), str(native / "sim_streaming.cpp"),
                    str(native / "vga_decoder.cpp"), "-o", str(library)], check=True, capture_output=True)
    return library, profile


def test_native_spi_response_modes_polarity_order_and_reset(spi_library):
    library, profile = spi_library
    with VerilatorSimulation(library, profile) as simulation:
        simulation.configure_drive_channels([("input_bus", 0, False)])
        for mode in range(4):
            for lsb in (False, True):
                for active_low in (False, True):
                    simulation.configure_spi_slaves([(0, 0, 1, 0, 0, mode, lsb, active_low, 0x96)])
                    idle = bool(mode & 2)

                    def update(clock, selected):
                        simulation.set_input("controls", int(clock) | (int(not selected if active_low else selected) << 1))
                        simulation.ticks(2)
                        return simulation.get_output("echo") & 1

                    simulation.set_input("input_bus", 2)
                    assert update(idle, False) == 0
                    update(idle, True)
                    for _ in range(2):
                        bits = []
                        for index in range(8):
                            if mode & 1:
                                bits.append(update(not idle, True))
                                update(idle, True)
                            else:
                                bits.append(simulation.get_output("echo") & 1)
                                update(not idle, True)
                                update(idle, True)
                        expected = [(0x96 >> (i if lsb else 7-i)) & 1 for i in range(8)]
                        assert bits == expected
                    assert simulation.get_output("echo") & 2 == 2
                    assert update(idle, False) == 0
                    update(idle, True)
                    update(not idle, True)
                    simulation.reset()
                    update(idle, False)
                    update(idle, True)
                    assert update(not idle, True) == expected[0]
        with pytest.raises(ValueError):
            simulation.configure_spi_slaves([(0, 0, 1, 0, 9, 0, False, True, 0x96)])
        with pytest.raises(ValueError, match="reserved"):
            simulation.enqueue_drive_events([(0, simulation.drive_cycle() + 1, True)])
        simulation.configure_spi_slaves([])
        assert simulation.get_output("echo") & 1 == 0
        simulation.enqueue_drive_events([(0, simulation.drive_cycle() + 1, True)])
        simulation.ticks(1)
        assert simulation.get_output("echo") & 1 == 1


def test_spi_response_requires_one_hex_byte():
    assert spi_response_byte("0xa5") == 165
    assert spi_response_byte(" 31 ") == 49
    for invalid in ("", "A", "A500", "GG", 165):
        with pytest.raises(ValueError, match="hexadecimal"):
            spi_response_byte(invalid)
