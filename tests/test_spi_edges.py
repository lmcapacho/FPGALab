"""SPI decoding and workbench delivery over the generic edge-stream API."""

import json
import os
from pathlib import Path
import shutil

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication

_APPLICATION = QApplication.instance() or QApplication([])

from fpga_lab.peripherals.manifest import parse_manifest
from fpga_lab.simulation import EdgeEvent
from fpga_lab.spi_edges import SpiDecoder


def _spi_transitions(value=0x96, *, mode=0, bit_order="msb"):
    idle_clock = bool(mode & 2)
    levels = {"sck": idle_clock, "mosi": False, "cs": True}
    events = [(1, terminal, level) for terminal, level in levels.items()]
    events.append((10, "cs", False))
    bits = [(value >> (index if bit_order == "lsb" else 7 - index)) & 1 for index in range(8)]
    for index, bit in enumerate(bits):
        cycle = 12 + 4 * index
        events.extend(((cycle - 1, "mosi", bool(bit)), (cycle, "sck", not idle_clock),
                       (cycle + 2, "sck", idle_clock)))
    events.append((46, "cs", True))
    return sorted(events, key=lambda event: event[0])


@pytest.mark.parametrize("mode", [0, 1, 2, 3])
@pytest.mark.parametrize("bit_order", ["msb", "lsb"])
def test_spi_decodes_all_modes_across_frame_boundaries(mode, bit_order):
    decoder = SpiDecoder(mode, bit_order)
    events = _spi_transitions(mode=mode, bit_order=bit_order)
    first = [event for event in events if event[0] <= 27]
    second = [event for event in events if event[0] > 27]
    assert decoder.feed(first, 27) == []
    assert [(byte.transaction, byte.mosi, byte.miso) for byte in decoder.feed(second, 46)] == [
        (1, 0x96, None),
    ]


def test_spi_discards_partial_transfer_when_chip_select_releases():
    decoder = SpiDecoder()
    events = _spi_transitions()[:12]
    events.append((25, "cs", True))
    assert decoder.feed(events, 25) == []
    assert decoder.partial_bits > 0
    decoder.reset()
    assert decoder.feed(_spi_transitions(), 46)[0].mosi == 0x96


def test_spi_manifest_and_workbench_route_ordered_multichannel_edges(tmp_path, monkeypatch):
    from fpga_lab.board import BoardDefinition, bundled_board_definition
    from fpga_lab.peripherals.catalog import load_catalog
    from fpga_lab.peripherals_panel import PeripheralsPanel
    from fpga_lab.simulation_worker import EdgeFrame, SimulationFrame
    from fpga_lab.workbench.item import WorkbenchPeripheralItem

    source = Path(__file__).parents[1] / "examples/peripherals/spi_monitor"
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    assert parse_manifest(manifest, resource_root=source).edge_channels == ("sck", "mosi", "cs")
    manifest["visual"]["clock_channel"] = "not_a_channel"
    with pytest.raises(ValueError, match="spi_monitor"):
        parse_manifest(manifest, resource_root=source)

    catalog = tmp_path / "catalog"
    shutil.copytree(source, catalog / "spi_monitor")
    monkeypatch.setenv("FPGALAB_PERIPHERALS_DIR", str(catalog))
    load_catalog.cache_clear()
    try:
        lab = tmp_path / "lab.json"
        lab.write_text(json.dumps({"peripherals": [{
            "id": "spi_1", "type": "spi_monitor",
            "connections": {"sck": "D0", "mosi": "D1", "cs": "D2"},
            "properties": {"mode": "0", "bit_order": "msb", "cs_polarity": "low"},
        }]}), encoding="utf-8")
        pcf = tmp_path / "design.pcf"
        pcf.write_text("set_io sck 2\nset_io mosi 1\nset_io cs 4\n", encoding="utf-8")
        board = BoardDefinition.load(bundled_board_definition())
        panel = PeripheralsPanel(board, pcf, lab, output_widths={"sck": 1, "mosi": 1, "cs": 1})
        assert panel.edge_channels() == [(0, 0), (1, 0), (2, 0)]
        panel.set_powered(True)
        item = next(item for item in panel._workbench_scene.items() if isinstance(item, WorkbenchPeripheralItem))
        indexes = {"sck": 0, "mosi": 1, "cs": 2}
        events = _spi_transitions()
        for last in (27, 46):
            chunk = tuple(EdgeEvent(cycle, indexes[terminal], level)
                          for cycle, terminal, level in events if (cycle <= 27 if last == 27 else cycle > 27))
            panel.update_frame(SimulationFrame(
                led_brightness=(0.0,) * 8, outputs={},
                edge_stream=EdgeFrame(last, 1_000_000, chunk, 0),
            ))
        assert "MOSI 96" in item._rx_output.toPlainText()
        assert item._rx_caption.text() == "SPI"
        panel.deleteLater()
    finally:
        load_catalog.cache_clear()
