"""Input routing coverage for workbench peripherals."""

from __future__ import annotations

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from fpga_lab.board import BoardDefinition, bundled_board_definition
from fpga_lab.peripherals_panel import PeripheralConfigDialog, PeripheralsPanel
from fpga_lab.wiring import PeripheralInstance


_APPLICATION = QApplication.instance() or QApplication([])


def test_button_routes_a_scalar_pcf_net(tmp_path):
    board = BoardDefinition.load(bundled_board_definition())
    lab = tmp_path / "lab.json"
    lab.write_text(
        json.dumps({
            "peripherals": [{
                "id": "button_1",
                "type": "button",
                "connections": {"signal": "D3"},
                "properties": {},
            }],
        }),
        encoding="utf-8",
    )
    pcf = tmp_path / "main.pcf"
    pcf.write_text(f"set_io input_signal {board.fpga_pin_for('D3')}\n", encoding="utf-8")
    panel = PeripheralsPanel(board, pcf, lab, {"input_signal": 1})
    values: list[tuple[str, int]] = []
    panel.input_changed.connect(lambda name, value: values.append((name, value)))

    panel._drive_input("button_1", "signal", 1)
    panel._drive_input("button_1", "signal", 0)

    assert values == [("input_signal", 1), ("input_signal", 0)]
    panel.deleteLater()
    assert _APPLICATION is not None


def test_anode_display_with_ground_common_never_falls_back_to_raw_segments(tmp_path):
    board = BoardDefinition.load(bundled_board_definition())
    terminals = ("a", "b", "c", "d", "e", "f", "g")
    endpoints = ("D4", "D5", "D6", "D7", "D8", "D9", "D10")
    lab = tmp_path / "lab.json"
    lab.write_text(
        json.dumps({
            "peripherals": [{
                "id": "display_1",
                "type": "seven_segment",
                "connections": {**dict(zip(terminals, endpoints)), "common": "GND"},
                "properties": {"common": "anode"},
            }],
        }),
        encoding="utf-8",
    )
    pcf = tmp_path / "main.pcf"
    pcf.write_text(
        "\n".join(
            f"set_io segment_{terminal} {board.fpga_pin_for(endpoint)}"
            for terminal, endpoint in zip(terminals, endpoints)
        ) + "\n",
        encoding="utf-8",
    )
    panel = PeripheralsPanel(
        board,
        pcf,
        lab,
        output_widths={f"segment_{terminal}": 1 for terminal in terminals},
    )

    assert panel.temporal_probes() == []
    assert {("display_1", terminal) for terminal in terminals} <= panel._temporal_terminals
    panel.deleteLater()
    assert _APPLICATION is not None


def test_switching_labs_rebuilds_the_workbench(tmp_path):
    board = BoardDefinition.load(bundled_board_definition())
    first_lab = tmp_path / "first.lab.json"
    first_lab.write_text(
        json.dumps({
            "peripherals": [{
                "id": "led_1",
                "type": "led",
                "connections": {"anode": "D0"},
                "properties": {},
            }],
        }),
        encoding="utf-8",
    )
    second_lab = tmp_path / "second.lab.json"
    second_lab.write_text(
        json.dumps({
            "peripherals": [{
                "id": "button_1",
                "type": "button",
                "connections": {"signal": "D1"},
                "properties": {},
            }, {
                "id": "sensor_1",
                "type": "sensor",
                "connections": {"signal": "D2"},
                "properties": {},
            }],
        }),
        encoding="utf-8",
    )
    panel = PeripheralsPanel(board, None, first_lab)

    panel.set_lab_file(second_lab)

    identifiers = {
        item.peripheral.peripheral_id
        for item in panel._workbench_scene.items()
        if hasattr(item, "peripheral")
    }
    assert identifiers == {"button_1", "sensor_1"}
    panel.deleteLater()


def test_workbench_zoom_is_optional_and_persisted_per_lab(tmp_path):
    board = BoardDefinition.load(bundled_board_definition())
    lab = tmp_path / "lab.json"
    lab.write_text(json.dumps({"peripherals": []}), encoding="utf-8")

    panel = PeripheralsPanel(board, None, lab)
    assert panel.workbench._zoom == 1.0
    panel.workbench.set_zoom(0.8)
    panel.deleteLater()

    raw = json.loads(lab.read_text(encoding="utf-8"))
    assert raw["workbench"]["zoom"] == 0.8
    restored = PeripheralsPanel(board, None, lab)
    assert restored.workbench._zoom == 0.8
    restored.deleteLater()


def test_conflicting_input_remains_open_and_clears_only_that_pin():
    board = BoardDefinition.load(bundled_board_definition())
    dialog = PeripheralConfigDialog(
        PeripheralInstance("button_2", "button", {"signal": "D3"}, {}),
        board,
    )

    dialog.show_error("Input conflict: more than one peripheral drives D3.", "D3")

    assert dialog.result() == 0
    assert dialog._pickers["signal"].currentData() == ""
    assert dialog._error_label.isVisible() is False
    dialog.show()
    assert dialog._error_label.isVisible()
    dialog.close()
