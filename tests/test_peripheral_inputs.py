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
