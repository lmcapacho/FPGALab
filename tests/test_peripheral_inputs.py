"""Input routing coverage for workbench peripherals."""

from __future__ import annotations

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPointF, QSettings, Qt
from PyQt6.QtWidgets import QApplication, QGraphicsView, QMessageBox

from fpga_lab.board import BoardDefinition, bundled_board_definition
from fpga_lab.peripherals_panel import PeripheralConfigDialog, PeripheralsPanel
from fpga_lab.lab_workspace import LabWorkspace
from fpga_lab.main_window import FPGALabMainWindow, LabManagerDialog
from fpga_lab.simulation_worker import SimulationFrame
from fpga_lab.virtual_lab import FPGAVirtualLab
from fpga_lab.wiring import PeripheralInstance


_APPLICATION = QApplication.instance() or QApplication([])


def test_deleting_the_active_lab_immediately_selects_the_starter_lab(tmp_path, monkeypatch):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    workspace = LabWorkspace(tmp_path / "workspace", settings)
    active = workspace.create("Active")
    workspace.remember_selected(active.path)
    dialog = LabManagerDialog(workspace, active.path)
    replacements: list[object] = []
    dialog.active_lab_changed.connect(replacements.append)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )

    dialog._delete_lab()

    starter = workspace.ensure_default().resolve()
    assert active.path.exists() is False
    assert replacements == [starter]
    assert dialog.selected_lab().resolve() == starter
    dialog.close()
    dialog.deleteLater()


def test_model_changing_controls_are_locked_while_running(tmp_path):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    window = FPGALabMainWindow(LabWorkspace(tmp_path / "labs", settings))

    window.set_simulation_running(True)

    assert window._run_button.isEnabled() is False
    assert window._stop_button.isEnabled() is True
    assert window._browse_button.isEnabled() is False
    assert window._recent.isEnabled() is False
    assert window._lab_button.isEnabled() is False
    assert window._simulation_settings_button.isEnabled() is False
    assert window._language.isEnabled() is True
    assert window._toolchain_button.isEnabled() is True

    window.set_simulation_running(False)

    assert window._run_button.isEnabled() is True
    assert window._stop_button.isEnabled() is False
    assert window._browse_button.isEnabled() is True
    assert window._recent.isEnabled() is True
    assert window._lab_button.isEnabled() is True
    assert window._simulation_settings_button.isEnabled() is True
    window.close()
    window.deleteLater()


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
    lab.clock_performance_changed.connect(
        lambda requested, achieved: measurements.append((requested, achieved))
    )
    frame = SimulationFrame(led_brightness=(0.0,) * 8, outputs={}, virtual_hz=8_000_000)

    lab._running = True
    lab._paint_state(frame)
    lab.stop_simulation()
    lab._paint_state(frame)

    assert measurements == [(12_000_000.0, 8_000_000.0)]
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


def test_fit_contents_uses_and_persists_the_regular_workbench_zoom(tmp_path):
    board = BoardDefinition.load(bundled_board_definition())
    lab = tmp_path / "fit.lab"
    lab.write_text(json.dumps({
        "peripherals": [
            {"id": "led_1", "type": "led", "connections": {}, "properties": {"position": [10, 10]}},
            {"id": "led_2", "type": "led", "connections": {}, "properties": {"position": [500, 350]}},
        ],
    }), encoding="utf-8")
    panel = PeripheralsPanel(board, None, lab)
    panel.resize(760, 520)
    panel.show()
    _APPLICATION.processEvents()
    panel.workbench.set_zoom(2.0)

    panel.workbench.fit_contents()

    raw = json.loads(lab.read_text(encoding="utf-8"))
    assert 0.1 <= panel.workbench._zoom < 2.0
    assert raw["workbench"]["zoom"] == round(panel.workbench._zoom, 4)
    panel.close()
    panel.deleteLater()


def test_workbench_camera_is_persisted_with_zoom(tmp_path):
    board = BoardDefinition.load(bundled_board_definition())
    lab = tmp_path / "camera.lab"
    lab.write_text('{"peripherals": []}', encoding="utf-8")
    panel = PeripheralsPanel(board, None, lab)

    panel.workbench.set_zoom(0.5)
    panel.workbench.centerOn(QPointF(-320.0, 740.0))
    panel.workbench.camera_changed.emit(panel.workbench.camera_center())

    raw = json.loads(lab.read_text(encoding="utf-8"))
    assert raw["workbench"]["zoom"] == 0.5
    assert len(raw["workbench"]["center"]) == 2
    restored = PeripheralsPanel(board, None, lab)
    assert restored.workbench._zoom == 0.5
    panel.deleteLater()
    restored.deleteLater()


def test_canvas_pan_pauses_outside_the_workbench_without_a_reentry_jump(tmp_path):
    class MoveEvent:
        def __init__(self, position: QPointF):
            self._position = position

        def position(self):
            return self._position

        def accept(self):
            pass

    board = BoardDefinition.load(bundled_board_definition())
    lab = tmp_path / "bounded-pan.lab"
    lab.write_text('{"peripherals": []}', encoding="utf-8")
    panel = PeripheralsPanel(board, None, lab)
    panel.resize(760, 520)
    panel.show()
    _APPLICATION.processEvents()
    view = panel.workbench
    original_center = view.camera_center()
    view._panning = True
    view._pan_start = QPointF(100.0, 100.0)
    view._pan_center = original_center

    view.mouseMoveEvent(MoveEvent(QPointF(-50.0, -50.0)))
    paused_center = view.camera_center()
    view.mouseMoveEvent(MoveEvent(QPointF(50.0, 50.0)))

    assert paused_center == original_center
    assert view.camera_center() == original_center
    panel.close()
    panel.deleteLater()


def test_workbench_uses_rubber_band_selection_and_persists_group_positions(tmp_path):
    board = BoardDefinition.load(bundled_board_definition())
    lab = tmp_path / "group.lab"
    lab.write_text(json.dumps({
        "peripherals": [
            {"id": "led_1", "type": "led", "connections": {}, "properties": {"position": [10, 10]}},
            {"id": "led_2", "type": "led", "connections": {}, "properties": {"position": [80, 10]}},
        ],
    }), encoding="utf-8")
    panel = PeripheralsPanel(board, None, lab)

    assert panel.workbench.dragMode() == QGraphicsView.DragMode.RubberBandDrag
    panel._save_positions([("led_1", 35.25, 42.75), ("led_2", 105.25, 42.75)])

    raw = json.loads(lab.read_text(encoding="utf-8"))
    positions = {item["id"]: item["properties"]["position"] for item in raw["peripherals"]}
    assert positions == {"led_1": [35.2, 42.8], "led_2": [105.2, 42.8]}
    panel.deleteLater()


def test_group_movement_can_be_undone_and_redone(tmp_path):
    board = BoardDefinition.load(bundled_board_definition())
    lab = tmp_path / "history.lab"
    lab.write_text(json.dumps({
        "peripherals": [
            {"id": "led_1", "type": "led", "connections": {}, "properties": {"position": [10, 10]}},
            {"id": "led_2", "type": "led", "connections": {}, "properties": {"position": [80, 10]}},
        ],
    }), encoding="utf-8")
    panel = PeripheralsPanel(board, None, lab)

    panel._save_positions([("led_1", 30, 40), ("led_2", 100, 40)])
    panel.undo()
    undone = json.loads(lab.read_text(encoding="utf-8"))
    panel.redo()
    redone = json.loads(lab.read_text(encoding="utf-8"))

    assert [item["properties"]["position"] for item in undone["peripherals"]] == [[10, 10], [80, 10]]
    assert [item["properties"]["position"] for item in redone["peripherals"]] == [[30, 40], [100, 40]]
    panel.deleteLater()


def test_multiple_selected_peripherals_are_deleted_as_one_undoable_action(tmp_path, monkeypatch):
    board = BoardDefinition.load(bundled_board_definition())
    lab = tmp_path / "delete-group.lab"
    lab.write_text(json.dumps({
        "peripherals": [
            {"id": "led_1", "type": "led", "connections": {}, "properties": {}},
            {"id": "led_2", "type": "led", "connections": {}, "properties": {}},
        ],
    }), encoding="utf-8")
    panel = PeripheralsPanel(board, None, lab)
    peripherals = [
        item.peripheral for item in panel._workbench_scene.items()
        if hasattr(item, "peripheral")
    ]
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )

    panel._delete_many(peripherals)
    deleted = json.loads(lab.read_text(encoding="utf-8"))
    panel.undo()
    restored = json.loads(lab.read_text(encoding="utf-8"))

    assert deleted["peripherals"] == []
    assert {item["id"] for item in restored["peripherals"]} == {"led_1", "led_2"}
    assert panel._history_index == 0
    panel.deleteLater()


def test_workbench_history_survives_a_lab_widget_replacement(tmp_path):
    board = BoardDefinition.load(bundled_board_definition())
    lab = tmp_path / "replacement.lab"
    lab.write_text(json.dumps({
        "peripherals": [
            {"id": "led_1", "type": "led", "connections": {}, "properties": {"position": [10, 10]}},
        ],
    }), encoding="utf-8")
    original = PeripheralsPanel(board, None, lab)
    original._save_positions([("led_1", 70, 80)])

    replacement = PeripheralsPanel(board, None, lab)
    replacement.restore_history_state(original.history_state())
    replacement.set_editable(False)
    replacement.set_editable(True)
    replacement.undo()

    raw = json.loads(lab.read_text(encoding="utf-8"))
    assert raw["peripherals"][0]["properties"]["position"] == [10, 10]
    original.deleteLater()
    replacement.deleteLater()


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
