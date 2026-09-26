"""End-to-end edge ABI and frame-spanning UART decoding."""

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication

_APPLICATION = QApplication.instance() or QApplication([])

from fpga_lab.cpp_wrapper import render_cpp_wrapper
from fpga_lab.peripherals.manifest import parse_manifest
from fpga_lab.profile import BoardProfile
from fpga_lab.serial_edges import Transition, Uart8N1Decoder
from fpga_lab.simulation import EdgeEvent, VerilatorSimulation


def _uart_edges(value: int, start: int, bit_cycles: int = 100) -> list[Transition]:
    levels = [False, *(bool(value & (1 << bit)) for bit in range(8)), True]
    previous = True
    edges = []
    for index, level in enumerate(levels):
        if level != previous:
            edges.append(Transition(start + index * bit_cycles, level))
        previous = level
    return edges


def test_uart_decoder_keeps_partial_bytes_across_ui_frames():
    decoder = Uart8N1Decoder(1_000_000, 10_000)
    edges = [Transition(1, True), *_uart_edges(ord("A"), 100), *_uart_edges(10, 1200)]
    first = [edge for edge in edges if edge.cycle <= 650]
    second = [edge for edge in edges if 650 < edge.cycle <= 1600]
    last = [edge for edge in edges if edge.cycle > 1600]
    assert decoder.feed(first, 650) == []
    assert decoder.feed(second, 1600) == [ord("A")]
    assert decoder.feed(last, 2300) == [10]
    assert decoder.framing_errors == 0


def test_uart_rejects_invalid_baud_and_malformed_stop_bit():
    with pytest.raises(ValueError):
        Uart8N1Decoder(1_000_000, 600_000)
    decoder = Uart8N1Decoder(1_000_000, 10_000)
    edges = _uart_edges(0, 100)
    # Hold the line low during the stop-bit sample.
    assert decoder.feed(edges[:-1], 1100) == []
    assert decoder.framing_errors == 1


def test_external_uart_manifest_uses_edge_api_v2():
    directory = Path(__file__).parents[1] / "examples/peripherals/uart_terminal"
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    spec = parse_manifest(manifest, resource_root=directory)
    assert spec.edge_channels == ("rx",)
    assert spec.visual["renderer"] == "uart_terminal"
    manifest["api_version"] = 1
    with pytest.raises(ValueError, match="api_version 2"):
        parse_manifest(manifest)


def test_uart_renderer_receives_byte_stream_and_resets_on_power_off():
    from PyQt6.QtGui import QImage, QPainter
    from fpga_lab.peripherals.renderers.uart_terminal import UartTerminalRenderer
    from fpga_lab.wiring import PeripheralInstance

    assert _APPLICATION is not None
    peripheral = PeripheralInstance("uart_1", "uart_terminal", {}, {"baud": "10000"})
    renderer = UartTerminalRenderer({"size": [300, 170], "channel": "rx", "baud_property": "baud"})
    events = [EdgeEvent(edge.cycle, 0, edge.level) for edge in _uart_edges(ord("A"), 100)]
    renderer.feed_edges(peripheral, "rx", events[:3], 450, 1_000_000, 0)
    renderer.feed_edges(peripheral, "rx", events[3:], 1100, 1_000_000, 0)
    assert renderer._text == "A"
    image = QImage(300, 170, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    try:
        renderer.paint(painter, None, peripheral, {"powered": True})
    finally:
        painter.end()
    renderer.reset_stream()
    assert renderer._text == ""


def test_external_manifest_channels_reach_the_workbench(tmp_path, monkeypatch):
    from fpga_lab.board import BoardDefinition, bundled_board_definition
    from fpga_lab.peripherals.catalog import load_catalog
    from fpga_lab.peripherals_panel import PeripheralsPanel
    from fpga_lab.simulation_worker import EdgeFrame, SimulationFrame
    from fpga_lab.workbench.item import WorkbenchPeripheralItem

    assert _APPLICATION is not None
    catalog = tmp_path / "catalog"
    shutil.copytree(Path(__file__).parents[1] / "examples/peripherals/uart_terminal", catalog / "uart_terminal")
    monkeypatch.setenv("FPGALAB_PERIPHERALS_DIR", str(catalog))
    load_catalog.cache_clear()
    try:
        lab = tmp_path / "lab.json"
        lab.write_text(json.dumps({"peripherals": [{
            "id": "uart_1", "type": "uart_terminal",
            "connections": {"rx": "D0"}, "properties": {"baud": "10000"},
        }]}), encoding="utf-8")
        pcf = tmp_path / "design.pcf"
        pcf.write_text("set_io tx 2\n", encoding="utf-8")
        board = BoardDefinition.load(bundled_board_definition())
        panel = PeripheralsPanel(board, pcf, lab, output_widths={"tx": 1})
        assert panel.edge_channels() == [(0, 0)]
        panel.set_powered(True)
        edges = tuple(EdgeEvent(edge.cycle, 0, edge.level) for edge in _uart_edges(ord("A"), 100))
        frame = SimulationFrame(
            led_brightness=(0.0,) * 8,
            outputs={"tx": 1},
            edge_stream=EdgeFrame(1100, 1_000_000, edges, 0),
        )
        panel.update_frame(frame)
        items = [item for item in panel._workbench_scene.items() if isinstance(item, WorkbenchPeripheralItem)]
        assert len(items) == 1
        assert items[0]._renderer._text == "A"
        panel.deleteLater()
    finally:
        load_catalog.cache_clear()


def test_generated_native_edge_capture_retains_cycle_timestamps(tmp_path):
    if shutil.which("g++") is None:
        pytest.skip("g++ is not available")
    profile = BoardProfile("test", {"clk": 1}, {"tx": 1}, {"tx": 1}, "clk")
    (tmp_path / "wrapper.cpp").write_text(render_cpp_wrapper(profile), encoding="utf-8")
    (tmp_path / "verilated.h").write_text(
        "#pragma once\n#include <cstdint>\nclass VerilatedContext { public: void timeInc(uint64_t) {} };\n",
        encoding="utf-8",
    )
    (tmp_path / "Vtop.h").write_text(
        '#pragma once\n#include "verilated.h"\n'
        "class Vtop { public: uint8_t clk=0, tx=1; int cycle=0; "
        "explicit Vtop(VerilatedContext*) {} "
        "void eval() { if (clk) { tx = ((cycle / 10) % 2) == 0; ++cycle; } } "
        "void final() {} };\n",
        encoding="utf-8",
    )
    source_root = Path(__file__).parents[1]
    native = source_root / "fpga_lab/native"
    library = tmp_path / "libtest.so"
    subprocess.run(
        ["g++", "-std=c++17", "-shared", "-fPIC", "-O2", "-I", str(tmp_path),
         "-I", str(native), str(tmp_path / "wrapper.cpp"),
         str(native / "sim_streaming.cpp"), str(native / "vga_decoder.cpp"), "-o", str(library)],
        check=True,
        capture_output=True,
        text=True,
    )
    with VerilatorSimulation(library, profile) as simulation:
        simulation.configure_edge_channels([(0, 0)])
        simulation.ticks(25)
        cycle, events, dropped = simulation.edge_window()
        assert (cycle, dropped) == (25, 0)
        assert [(event.cycle, event.level) for event in events] == [(1, True), (11, False), (21, True)]
        simulation.ticks(15)
        cycle, events, dropped = simulation.edge_window()
        assert (cycle, dropped) == (40, 0)
        assert [(event.cycle, event.level) for event in events] == [(31, False)]
        simulation.reset()
        assert simulation.edge_window() == (0, [], 0)
        simulation.ticks(2)
        assert [(event.cycle, event.level) for event in simulation.edge_window()[1]] == [(1, True)]
        simulation.ticks(200_000)
        cycle, events, dropped = simulation.edge_window()
        assert cycle == 200_002
        assert len(events) == 16_384
        assert dropped > 0
        assert simulation.edge_window() == (200_002, [], 0)
