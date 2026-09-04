"""Input routing coverage for workbench peripherals."""

from __future__ import annotations

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from fpga_lab.board import BoardDefinition, bundled_board_definition
from fpga_lab.peripherals_panel import PeripheralsPanel


def test_button_routes_a_scalar_pcf_net(tmp_path):
    application = QApplication.instance() or QApplication([])
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
    assert application is not None
