"""Input routing coverage for workbench peripherals."""

from __future__ import annotations

import json
import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from fpga_lab.board import BoardDefinition, bundled_board_definition
from fpga_lab.peripherals_panel import PeripheralConfigDialog, PeripheralsPanel
from fpga_lab.simulation_worker import SimulationFrame, TemporalFrame
from fpga_lab.virtual_lab import FPGAVirtualLab
from fpga_lab.wiring import PeripheralInstance


_APPLICATION = QApplication.instance() or QApplication([])


def test_closing_a_running_worker_stops_its_thread_and_native_simulation(tmp_path):
    class FakeSimulation:
        profile = SimpleNamespace(board_name="Test", inputs={}, outputs={}, clock_name="clk")

        def __init__(self):
            self.closed = False

        def set_observation_divisor(self, _divisor):
            pass

        def set_temporal_probes(self, _probes):
            pass

        def close(self):
            self.closed = True

    lab_file = tmp_path / "lab.json"
    lab_file.write_text('{"peripherals": []}', encoding="utf-8")
    simulation = FakeSimulation()
    lab = FPGAVirtualLab(simulation=simulation, lab_file=lab_file)
    thread = lab._thread
    assert thread is not None
    assert thread.isRunning()

    assert lab.close() is True

    assert thread.isRunning() is False
    assert simulation.closed is True
    lab.deleteLater()


def test_combinational_lab_starts_visual_refresh(tmp_path):
    """Static combinational outputs need visual frames after Run is pressed."""
    lab_file = tmp_path / "lab.json"
    lab_file.write_text('{"peripherals": []}', encoding="utf-8")
    lab = FPGAVirtualLab(lab_file=lab_file)
    requests: list[bool] = []
    lab.play_requested.connect(lambda: requests.append(True))

    lab.start_simulation()

    assert requests == [True]
    lab.close()
    lab.deleteLater()


def test_stopped_lab_ignores_queued_clock_measurements(tmp_path):
    lab_file = tmp_path / "lab.json"
    lab_file.write_text('{"peripherals": []}', encoding="utf-8")
    lab = FPGAVirtualLab(lab_file=lab_file)
    lab._has_clock = True
    measurements: list[tuple[float, float]] = []
    painted_frames: list[SimulationFrame] = []
    lab.clock_performance_changed.connect(
        lambda requested, achieved: measurements.append((requested, achieved))
    )
    lab._peripherals.update_frame = painted_frames.append
    frame = SimulationFrame(led_brightness=(0.0,) * 8, outputs={}, virtual_hz=8_000_000)

    lab._running = True
    lab._paint_state(frame)
    lab.stop_simulation()
    lab._paint_state(frame)

    assert measurements == [(12_000_000.0, 8_000_000.0)]
    assert painted_frames == [frame]
    lab.close()
    lab.deleteLater()


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

    panel.set_powered(True)
    panel._drive_input("button_1", "signal", 1)
    panel._drive_input("button_1", "signal", 0)

    assert values == [("input_signal", 1), ("input_signal", 0)]
    panel.deleteLater()


def test_stopped_panel_does_not_drive_combinational_inputs(tmp_path):
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
    panel.set_powered(True)
    panel._drive_input("button_1", "signal", 1)
    panel.set_powered(False)
    panel._drive_input("button_1", "signal", 0)

    assert values == [("input_signal", 1)]
    panel.deleteLater()


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


def test_temporal_output_preserves_raw_pwm_duty_separately_from_led_brightness(tmp_path):
    board = BoardDefinition.load(bundled_board_definition())
    lab = tmp_path / "pwm.lab"
    lab.write_text(json.dumps({
        "peripherals": [{
            "id": "led_1", "type": "led", "connections": {"anode": "D0"}, "properties": {},
        }],
    }), encoding="utf-8")
    pcf = tmp_path / "main.pcf"
    pcf.write_text(f"set_io pwm_signal {board.fpga_pin_for('D0')}\n", encoding="utf-8")
    panel = PeripheralsPanel(board, pcf, lab, output_widths={"pwm_signal": 1})
    assert len(panel.temporal_probes()) == 1
    item, terminal = panel._temporal_bindings[0]
    assert terminal == "anode"

    for hits, expected in ((25, 0.25), (50, 0.5), (75, 0.75)):
        panel._update_temporal_outputs(TemporalFrame((hits,), 100, (True,), (100,), 0.1))
        assert item._temporal_observations["anode"]["duty_cycle"] == expected
    assert item._brightness["anode"] != 0.75
    panel.deleteLater()


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


def test_new_peripheral_can_be_saved_with_required_terminals_not_connected(tmp_path):
    board = BoardDefinition.load(bundled_board_definition())
    lab_file = tmp_path / "lab.json"
    lab_file.write_text('{"peripherals": []}', encoding="utf-8")
    panel = PeripheralsPanel(board, None, lab_file)
    draft = PeripheralInstance("bcd_display_1", "bcd_display", {}, {})
    dialog = PeripheralConfigDialog(draft, board, parent=panel)
    messages: list[str] = []
    panel.changed.connect(messages.append)

    panel._save_new_peripheral(dialog, "bcd_display", set())

    saved = json.loads(lab_file.read_text(encoding="utf-8"))["peripherals"][0]
    assert saved["connections"] == {}
    assert panel.missing_required_connections() == (
        "bcd_display_1.A", "bcd_display_1.B", "bcd_display_1.C", "bcd_display_1.D",
    )
    assert "bcd_display_1 saved with required terminals not connected: A, B, C, D." in messages
    dialog.deleteLater()
    panel.deleteLater()


def test_workbench_opens_newer_lab_with_unsupported_peripheral_without_rewriting_it(tmp_path):
    board = BoardDefinition.load(bundled_board_definition())
    lab_file = tmp_path / "newer.lab"
    original = {
        "peripherals": [{
            "id": "led_bar_1",
            "type": "led_bar",
            "connections": {"LED0": "D0"},
            "properties": {"position": [30, 40], "future_property": 7},
        }],
    }
    lab_file.write_text(json.dumps(original, indent=2) + "\n", encoding="utf-8")

    panel = PeripheralsPanel(board, None, lab_file)
    items = [item for item in panel._workbench_scene.items() if hasattr(item, "supported")]

    assert len(items) == 1
    assert items[0].supported is False
    assert panel._compatibility_notice.isVisibleTo(panel)
    assert "led_bar_1" in panel._compatibility_notice.text()
    assert json.loads(lab_file.read_text(encoding="utf-8")) == original
    panel.deleteLater()
