"""Workbench layout, navigation, and undoable editing."""

from __future__ import annotations

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPointF, QSettings
from PyQt6.QtWidgets import QApplication, QGraphicsView, QMessageBox

from fpga_lab.board import BoardDefinition, bundled_board_definition
from fpga_lab.i18n import language_manager
from fpga_lab.peripherals_panel import PeripheralConfigDialog, PeripheralsPanel
from fpga_lab.virtual_lab import FPGAVirtualLab
from fpga_lab.wiring import PeripheralInstance
from fpga_lab.workbench.annotation import WorkbenchAnnotationItem


_APPLICATION = QApplication.instance() or QApplication([])


def test_annotation_menu_updates_when_language_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(language_manager, "_language", "en")
    lab = tmp_path / "annotations.lab"
    lab.write_text('{"peripherals": []}', encoding="utf-8")
    panel = PeripheralsPanel(BoardDefinition.load(bundled_board_definition()), None, lab)
    assert [action.text() for action in panel._annotation_menu.actions()] == [
        "Text", "Rectangle", "Ellipse", "Line",
    ]

    monkeypatch.setattr(language_manager, "_language", "es")
    language_manager.language_changed.emit("es")
    assert panel._annotation_button.text() == "Anotar"
    assert [action.text() for action in panel._annotation_menu.actions()] == [
        "Texto", "Rectángulo", "Elipse", "Línea",
    ]
    monkeypatch.setattr(language_manager, "_language", "en")
    language_manager.language_changed.emit("en")
    assert [action.text() for action in panel._annotation_menu.actions()] == [
        "Text", "Rectangle", "Ellipse", "Line",
    ]
    panel.close()
    panel.deleteLater()


def test_board_workbench_split_is_remembered_per_user(tmp_path):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    lab_file = tmp_path / "lab.json"
    lab_file.write_text('{"peripherals": []}', encoding="utf-8")
    first = FPGAVirtualLab(lab_file=lab_file, settings=settings)
    first.resize(1000, 600)
    first.show()
    _APPLICATION.processEvents()

    first._splitter.moveSplitter(350, 1)
    _APPLICATION.processEvents()
    saved_ratio = float(settings.value("ui/board_workbench_ratio"))

    second = FPGAVirtualLab(lab_file=lab_file, settings=settings)
    second.resize(1000, 600)
    second.show()
    _APPLICATION.processEvents()
    restored_sizes = second._splitter.sizes()
    restored_ratio = restored_sizes[0] / sum(restored_sizes)

    assert 0.3 < saved_ratio < 0.4
    assert abs(restored_ratio - saved_ratio) < 0.02
    first.close()
    second.close()
    first.deleteLater()
    second.deleteLater()


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


def test_new_peripheral_appears_at_current_camera_center(tmp_path):
    board = BoardDefinition.load(bundled_board_definition())
    lab = tmp_path / "new-at-camera.lab"
    lab.write_text('{"peripherals": []}', encoding="utf-8")
    panel = PeripheralsPanel(board, None, lab)
    panel.resize(760, 520)
    panel.show()
    _APPLICATION.processEvents()
    panel.workbench.set_zoom(0.5)
    panel.workbench.centerOn(QPointF(1200.0, -850.0))
    camera_before = panel.workbench.camera_center()

    draft = PeripheralInstance("led_1", "led", {}, {})
    dialog = PeripheralConfigDialog(draft, board, parent=panel)
    panel._save_new_peripheral(dialog, "led", set())

    raw = json.loads(lab.read_text(encoding="utf-8"))
    item = next(item for item in panel._workbench_scene.items() if hasattr(item, "peripheral"))
    visual_center = item.sceneBoundingRect().center()
    camera_after = panel.workbench.camera_center()
    assert raw["workbench"]["zoom"] == 0.5
    assert raw["workbench"]["center"] == [round(camera_before.x(), 2), round(camera_before.y(), 2)]
    assert abs(visual_center.x() - camera_before.x()) < 2
    assert abs(visual_center.y() - camera_before.y()) < 2
    assert abs(camera_after.x() - camera_before.x()) < 5
    assert abs(camera_after.y() - camera_before.y()) < 5
    assert panel.workbench.viewport().rect().contains(panel.workbench.mapFromScene(visual_center))
    panel.close()
    panel.deleteLater()


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
    monkeypatch.setattr(language_manager, "_language", "es")
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
    questions = []
    messages = []
    panel.changed.connect(messages.append)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda parent, title, prompt: (questions.append((title, prompt)) or QMessageBox.StandardButton.Yes),
    )

    panel._delete_many(peripherals)
    assert questions == [("Eliminar periféricos", "¿Eliminar los 2 periféricos seleccionados?")]
    assert messages[-1] == "2 periféricos eliminados"
    deleted = json.loads(lab.read_text(encoding="utf-8"))
    panel.undo()
    restored = json.loads(lab.read_text(encoding="utf-8"))

    assert deleted["peripherals"] == []
    assert {item["id"] for item in restored["peripherals"]} == {"led_1", "led_2"}
    assert panel._history_index == 0
    panel.deleteLater()


def test_delete_messages_distinguish_annotations_and_mixed_selections(tmp_path, monkeypatch):
    monkeypatch.setattr(language_manager, "_language", "es")
    lab = tmp_path / "delete-annotations.lab"
    lab.write_text(json.dumps({
        "peripherals": [{"id": "led_1", "type": "led", "connections": {}, "properties": {}}],
        "annotations": [
            {"id": "text_1", "type": "text", "text": "Note", "position": [0, 0], "width": 120, "height": 60},
            {"id": "text_2", "type": "text", "text": "Note", "position": [150, 0], "width": 120, "height": 60},
        ],
    }), encoding="utf-8")
    panel = PeripheralsPanel(BoardDefinition.load(bundled_board_definition()), None, lab)
    annotations = [item.data for item in panel._workbench_scene.items() if isinstance(item, WorkbenchAnnotationItem)]
    first_annotation = next(item for item in annotations if item["id"] == "text_1")
    peripheral = next(item.peripheral for item in panel._workbench_scene.items() if hasattr(item, "peripheral"))
    questions = []
    messages = []
    panel.changed.connect(messages.append)

    def confirm(parent, title, prompt):
        questions.append((title, prompt))
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", confirm)

    panel._delete_many(annotations)
    assert questions[-1] == ("Eliminar anotaciones", "¿Eliminar las 2 anotaciones seleccionadas?")
    assert messages[-1] == "2 anotaciones eliminadas"
    assert json.loads(lab.read_text(encoding="utf-8"))["annotations"] == []
    panel.undo()

    panel._delete_many([first_annotation, peripheral])
    assert questions[-1] == (
        "Eliminar elementos seleccionados",
        "¿Eliminar los 2 elementos seleccionados (periféricos y anotaciones)?",
    )
    assert messages[-1] == "2 elementos eliminados"
    saved = json.loads(lab.read_text(encoding="utf-8"))
    assert saved["peripherals"] == []
    assert len(saved["annotations"]) == 1
    panel.undo()

    panel._delete_many([first_annotation])
    assert questions[-1] == ("Eliminar anotación", "¿Eliminar text_1?")
    assert messages[-1] == "Anotación text_1 eliminada"
    assert len(json.loads(lab.read_text(encoding="utf-8"))["peripherals"]) == 1
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


def test_annotations_preserve_markdown_and_undo_size_changes(tmp_path):
    lab = tmp_path / "annotations.lab"
    original = {
        "peripherals": [],
        "annotations": [{
            "id": "text_1", "type": "text", "text": "**Heading**\nA note",
            "position": [12, 16], "width": 120, "height": 60,
        }],
    }
    lab.write_text(json.dumps(original), encoding="utf-8")
    panel = PeripheralsPanel(BoardDefinition.load(bundled_board_definition()), None, lab)

    annotations = [item for item in panel._workbench_scene.items() if isinstance(item, WorkbenchAnnotationItem)]
    assert len(annotations) == 1
    assert annotations[0].data["text"] == "**Heading**\nA note"

    panel._save_positions([("text_1", 30, 40, 200, 100, False, "free")])
    changed = json.loads(lab.read_text(encoding="utf-8"))["annotations"][0]
    assert (changed["position"], changed["width"], changed["height"]) == ([30, 40], 200, 100)
    panel.undo()
    assert json.loads(lab.read_text(encoding="utf-8"))["annotations"] == original["annotations"]
    panel.redo()
    assert json.loads(lab.read_text(encoding="utf-8"))["annotations"][0]["text"] == "**Heading**\nA note"
    panel.deleteLater()
