"""Workbench layout, navigation, and undoable editing."""

from __future__ import annotations

import json
import os
import pytest

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


def test_clipboard_mixed_selection_across_labs_and_undo(tmp_path):
    from fpga_lab.workbench.item import WorkbenchPeripheralItem
    source, target = tmp_path / "source.lab", tmp_path / "target.lab"
    source.write_text(json.dumps({"peripherals": [{"id": "led_1", "type": "led", "connections": {"signal": "D0"}, "properties": {"position": [180, 47]}}], "annotations": [{"id": "note", "type": "rectangle", "position": [13, 17], "width": 100, "height": 70}]}))
    target.write_text('{"peripherals": []}')
    board = BoardDefinition.load(bundled_board_definition())
    first, second = PeripheralsPanel(board, None, source), PeripheralsPanel(board, None, target)
    try:
        for item in first._workbench_scene.items():
            if isinstance(item, (WorkbenchPeripheralItem, WorkbenchAnnotationItem)):
                item.setSelected(True)
        first._copy_selection()
        second._paste_selection()
        pasted = json.loads(target.read_text())
        led, note = pasted["peripherals"][0], pasted["annotations"][0]
        assert led["connections"] == {}
        assert [led["properties"]["position"][i] - note["position"][i] for i in range(2)] == pytest.approx([167, 30])
        assert len(second._workbench_scene.selectedItems()) == 2
        second._paste_selection()
        repeated = json.loads(target.read_text())
        assert repeated["peripherals"][1]["id"] != led["id"]
        assert repeated["peripherals"][1]["properties"]["position"][0] == pytest.approx(led["properties"]["position"][0] + 24, abs=2)
        second.undo()
        assert json.loads(target.read_text()) == pasted
        second.redo()
        assert json.loads(target.read_text()) == repeated
    finally:
        first.close()
        second.close()


def test_clipboard_rejects_invalid_data_and_disallows_paste_when_locked(tmp_path):
    from PyQt6.QtCore import QMimeData
    from fpga_lab.workbench.clipboard import MIME_TYPE
    lab = tmp_path / "clipboard.lab"
    lab.write_text('{"peripherals": []}')
    panel = PeripheralsPanel(BoardDefinition.load(bundled_board_definition()), None, lab)
    try:
        original = lab.read_text()
        for data in (b'not json', b'{"version": 99}', b'{"version": 1, "origin": [0, 0], "peripherals": [], "annotations": []}'):
            mime = QMimeData()
            mime.setData(MIME_TYPE, data)
            _APPLICATION.clipboard().setMimeData(mime)
            panel._paste_selection()
            assert lab.read_text() == original
        panel._editing_enabled = False
        panel._paste_selection()
        assert lab.read_text() == original
    finally:
        panel.close()


def test_workbench_clipboard_shortcuts_leave_embedded_text_input_alone(tmp_path):
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QLineEdit
    lab = tmp_path / "input.lab"
    lab.write_text('{"peripherals": []}')
    panel = PeripheralsPanel(BoardDefinition.load(bundled_board_definition()), None, lab)
    try:
        field = QLineEdit("UART text")
        proxy = panel._workbench_scene.addWidget(field)
        panel.show()
        field.setFocus()
        proxy.setFocus()
        field.selectAll()
        _APPLICATION.processEvents()
        QTest.keyClick(field, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
        assert _APPLICATION.clipboard().text() == "UART text"
        _APPLICATION.clipboard().setText("new text")
        QTest.keyClick(field, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
        assert field.text() == "new text"
        assert json.loads(lab.read_text()) == {"peripherals": []}
    finally:
        panel.close()


def test_grid_snap_group_drag_preserves_offsets_and_undo(tmp_path):
    from PyQt6.QtCore import Qt, QEvent
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtTest import QTest
    from fpga_lab.workbench.item import WorkbenchPeripheralItem
    lab = tmp_path / "snap.lab"
    raw = {
        "peripherals": [{"id": "led_1", "type": "led", "connections": {}, "properties": {"position": [180, 47]}}],
        "annotations": [{"id": "note", "type": "rectangle", "position": [13, 17], "width": 100, "height": 70}],
    }
    lab.write_text(json.dumps(raw), encoding="utf-8")
    panel = PeripheralsPanel(BoardDefinition.load(bundled_board_definition()), None, lab)
    try:
        panel.resize(1000, 550)
        panel.show()
        _APPLICATION.processEvents()
        original = json.loads(lab.read_text(encoding="utf-8"))
        panel._snap_button.click()
        assert [item["properties"]["position"] for item in json.loads(lab.read_text())["peripherals"]] == [[180, 47]]
        view = panel.workbench
        items = panel._workbench_scene.items()
        anchor = next(item for item in items if isinstance(item, WorkbenchAnnotationItem))
        led = next(item for item in items if isinstance(item, WorkbenchPeripheralItem))
        anchor.setSelected(True)
        led.setSelected(True)
        offset = led.pos() - anchor.pos()
        start = view.mapFromScene(anchor.pos() + QPointF(50, 30))
        finish = start + view.mapFromScene(QPointF(14, 18)) - view.mapFromScene(QPointF(0, 0))
        QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=start)
        event = QMouseEvent(QEvent.Type.MouseMove, QPointF(finish), QPointF(view.viewport().mapToGlobal(finish)),
                            Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        _APPLICATION.sendEvent(view.viewport(), event)
        QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=finish)
        assert anchor.pos() == QPointF(20, 40)
        assert led.pos() - anchor.pos() == offset
        saved = json.loads(lab.read_text(encoding="utf-8"))
        assert saved["workbench"]["snap_to_grid"] is True
        panel.undo()
        restored = json.loads(lab.read_text())
        assert restored["annotations"][0]["position"] == original["annotations"][0]["position"]
        assert restored["peripherals"][0]["properties"]["position"] == [180, 47]
        panel.redo()
        assert json.loads(lab.read_text())["annotations"][0]["position"] == [20, 40]
        panel._grid_spacing.setValue(40)
        panel._reload()
        assert panel.workbench._grid_snap and panel.workbench._grid_spacing == 40
    finally:
        panel.close()
        panel.deleteLater()


def test_dot_grid_is_visual_only_and_visibility_is_shared_across_labs(tmp_path, monkeypatch):
    from fpga_lab.workbench import view as view_module
    settings = QSettings(str(tmp_path / "grid.ini"), QSettings.Format.IniFormat)
    monkeypatch.setattr(view_module, "QSettings", lambda *_args: settings)
    paths = [tmp_path / "first.lab", tmp_path / "second.lab"]
    original = '{"peripherals": []}'
    for path in paths:
        path.write_text(original, encoding="utf-8")
    board = BoardDefinition.load(bundled_board_definition())
    first = PeripheralsPanel(board, None, paths[0])
    second = None
    try:
        first.resize(800, 500)
        first.show()
        _APPLICATION.processEvents()
        assert not first._grid_button.isChecked()
        plain = first.workbench.viewport().grab().toImage()
        first._grid_button.click()
        _APPLICATION.processEvents()
        dotted = first.workbench.viewport().grab().toImage()
        assert plain != dotted
        assert not first._workbench_scene.items()
        assert settings.value(view_module.WorkbenchView.GRID_VISIBLE_KEY, type=bool)
        second = PeripheralsPanel(board, None, paths[1])
        assert second._grid_button.isChecked()
        assert all(path.read_text(encoding="utf-8") == original for path in paths)
        second._grid_button.click()
        assert not settings.value(view_module.WorkbenchView.GRID_VISIBLE_KEY, type=bool)
    finally:
        first.close()
        first.deleteLater()
        if second is not None:
            second.close()
            second.deleteLater()


def test_grid_snap_options_default_safely_for_older_or_invalid_labs(tmp_path):
    board = BoardDefinition.load(bundled_board_definition())
    states = [None, "legacy", {"snap_to_grid": "false", "grid_spacing": 0},
              {"snap_to_grid": True, "grid_spacing": "bad"}]
    for index, state in enumerate(states):
        lab = tmp_path / f"grid-{index}.lab"
        raw = {"peripherals": []}
        if state is not None:
            raw["workbench"] = state
        lab.write_text(json.dumps(raw), encoding="utf-8")
        panel = PeripheralsPanel(board, None, lab)
        try:
            assert panel.workbench._grid_snap == (isinstance(state, dict) and state.get("snap_to_grid") is True)
            assert panel.workbench._grid_spacing == 20
            assert json.loads(lab.read_text()) == raw
        finally:
            panel.close()
            panel.deleteLater()


def test_annotation_menu_updates_when_language_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(language_manager, "_language", "en")
    lab = tmp_path / "annotations.lab"
    lab.write_text('{"peripherals": []}', encoding="utf-8")
    panel = PeripheralsPanel(BoardDefinition.load(bundled_board_definition()), None, lab)
    _APPLICATION.clipboard().clear()
    def labels():
        menu = panel.workbench._create_context_menu(QPointF(50, 60))
        submenu = menu.actions()[0].menu()
        result = menu.actions()[0].text(), [action.text() for action in submenu.actions()]
        menu.deleteLater()
        return result
    assert labels() == ("Add annotation", ["Text", "Line", "Rectangle", "Ellipse"])

    monkeypatch.setattr(language_manager, "_language", "es")
    language_manager.language_changed.emit("es")
    assert labels() == ("Agregar anotación", ["Texto", "Línea", "Rectángulo", "Elipse"])
    monkeypatch.setattr(language_manager, "_language", "en")
    language_manager.language_changed.emit("en")
    assert labels() == ("Add annotation", ["Text", "Line", "Rectangle", "Ellipse"])
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


def test_workbench_undo_does_not_revert_lab_clock_metadata(tmp_path):
    board = BoardDefinition.load(bundled_board_definition())
    lab = tmp_path / "clock-history.lab"
    lab.write_text(json.dumps({
        "metadata": {"board_id": "alhambra-ii"},
        "peripherals": [{
            "id": "led_1", "type": "led", "connections": {},
            "properties": {"position": [10, 10]},
        }],
    }), encoding="utf-8")
    panel = PeripheralsPanel(board, None, lab)
    panel._save_positions([("led_1", 30, 40)])
    raw = json.loads(lab.read_text(encoding="utf-8"))
    raw["metadata"]["virtual_clock_hz"] = 25_175_000
    lab.write_text(json.dumps(raw), encoding="utf-8")

    panel.undo()
    assert json.loads(lab.read_text(encoding="utf-8"))["metadata"]["virtual_clock_hz"] == 25_175_000
    panel.redo()
    assert json.loads(lab.read_text(encoding="utf-8"))["metadata"]["virtual_clock_hz"] == 25_175_000
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


def test_annotation_editor_updates_text_and_preserves_legacy_data(tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QDialog
    from fpga_lab.workbench.annotation_editor import AnnotationEditor
    lab = tmp_path / "edit.lab"
    annotation = {"id": "note", "type": "text", "text": "**Old**\nline", "position": [40, 60],
                  "width": 120, "height": 60, "future_property": {"keep": True}}
    raw = {"peripherals": [], "annotations": [annotation]}
    lab.write_text(json.dumps(raw))
    panel = PeripheralsPanel(BoardDefinition.load(bundled_board_definition()), None, lab)
    try:
        def save(dialog):
            dialog.text_field.setPlainText("**New**\nsecond line")
            return QDialog.DialogCode.Accepted
        monkeypatch.setattr(AnnotationEditor, "exec", save)
        panel._edit_annotation(annotation)
        saved = json.loads(lab.read_text())["annotations"][0]
        assert saved["id"] == "note" and saved["position"] == [40, 60]
        assert saved["future_property"] == {"keep": True}
        assert saved["height"] == 60 and saved["width"] == 120
        assert saved["text"] == "**New**\nsecond line"
        panel.undo()
        assert json.loads(lab.read_text()) == raw
        panel.redo()
        assert json.loads(lab.read_text())["annotations"][0] == saved
        monkeypatch.setattr(AnnotationEditor, "exec", lambda dialog: QDialog.DialogCode.Rejected)
        panel._edit_annotation(saved)
        assert json.loads(lab.read_text())["annotations"] == [saved]
        panel._add_annotation("text")
        assert json.loads(lab.read_text())["annotations"] == [saved]
    finally:
        panel.close()


def test_annotation_editor_validates_text_and_creates_shapes(tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QDialog
    from fpga_lab.workbench.annotation_editor import AnnotationEditor
    dialog = AnnotationEditor({"id": "text_1", "type": "text", "text": ""})
    dialog._save()
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert dialog.error_label.text()
    dialog.text_field.setPlainText("# Heading\n\nText")
    dialog._save()
    assert dialog.result() == QDialog.DialogCode.Accepted
    dialog.close()
    lab = tmp_path / "create.lab"
    lab.write_text('{"peripherals": []}')
    panel = PeripheralsPanel(BoardDefinition.load(bundled_board_definition()), None, lab)
    try:
        def unexpected_dialog(dialog):
            raise AssertionError("Shapes must be inserted without opening an editor")
        monkeypatch.setattr(AnnotationEditor, "exec", unexpected_dialog)
        position = QPointF(-1450, 630)
        menu = panel.workbench._create_context_menu(position)
        menu.actions()[0].menu().actions()[1].trigger()
        menu.deleteLater()
        saved = json.loads(lab.read_text())["annotations"][0]
        assert saved["orientation"] == "horizontal" and saved["height"] == 12
        assert saved["position"] == [-1450, 630]
        assert len(panel._workbench_scene.selectedItems()) == 1
        panel.undo()
        assert not json.loads(lab.read_text()).get("annotations")
        for kind in ("rectangle", "ellipse"):
            panel._add_annotation(kind, position)
            assert json.loads(lab.read_text())["annotations"][-1]["type"] == kind
        panel.set_editable(False)
        menu = panel.workbench._create_context_menu(position)
        assert not menu.actions()[0].isEnabled()
        menu.deleteLater()
    finally:
        panel.close()


@pytest.mark.parametrize("kind", ["line", "rectangle", "ellipse"])
def test_annotation_appearance_persists_renders_and_resets_without_geometry_changes(tmp_path, monkeypatch, kind):
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QColor, QImage, QPainter
    from PyQt6.QtWidgets import QColorDialog, QDialog
    from fpga_lab.workbench.annotation_editor import AnnotationEditor
    from fpga_lab.workbench.annotation_style import annotation_pen
    annotation = {"id": "note", "type": kind, "position": [10, 20], "width": 100,
                  "height": 12 if kind == "line" else 60, "orientation": "horizontal",
                  "future_property": {"keep": True}}
    lab = tmp_path / "appearance.lab"
    raw = {"peripherals": [], "annotations": [annotation]}
    lab.write_text(json.dumps(raw))
    panel = PeripheralsPanel(BoardDefinition.load(bundled_board_definition()), None, lab)
    try:
        # A canvas resize does not rebuild the item: edit with its stale data.
        panel._save_positions([("note", 70, 90, 100, annotation["height"], False, "horizontal")])
        panel._save_positions([("note", 70, 90, 200, annotation["height"], False, "horizontal")])
        current = json.loads(lab.read_text())["annotations"][0]
        resized_raw = json.loads(lab.read_text())
        def save(dialog):
            monkeypatch.setattr(QColorDialog, "getColor", lambda *args: QColor("#ff0000"))
            dialog._choose_color("stroke_color", "border_strong")
            dialog.stroke_width.setValue(4)
            dialog.stroke_style.setCurrentIndex(dialog.stroke_style.findData("dashed"))
            if dialog.fill_enabled is not None:
                dialog.fill_enabled.setChecked(True)
                monkeypatch.setattr(QColorDialog, "getColor", lambda *args: QColor("#00ff00"))
                dialog._choose_color("fill_color", "accent_surface")
            return QDialog.DialogCode.Accepted
        monkeypatch.setattr(AnnotationEditor, "exec", save)
        panel._edit_annotation(annotation)
        saved = json.loads(lab.read_text())["annotations"][0]
        for field in ("position", "width", "height", "future_property"):
            assert saved[field] == current[field]
        assert saved["stroke_color"] == "#ff0000"
        assert saved["stroke_style"] == "dashed"
        assert annotation_pen(saved).widthF() == 4
        assert annotation_pen(saved).style() == Qt.PenStyle.DashLine
        if kind == "line":
            dotted = annotation_pen({**saved, "stroke_style": "dotted"})
            assert dotted.capStyle() == Qt.PenCapStyle.RoundCap
            assert dotted.dashPattern() == [0.01, 2.5]
        panel.undo()
        assert json.loads(lab.read_text()) == resized_raw
        panel.redo()
        item = next(item for item in panel._workbench_scene.items() if isinstance(item, WorkbenchAnnotationItem))
        # A separate selection outline must not replace the configured paint.
        selected_colors = []
        for selected in (False, True):
            item.setSelected(selected)
            image = QImage(130, 90, QImage.Format.Format_ARGB32)
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            painter.translate(10, 10)
            item.paint(painter, None)
            painter.end()
            selected_colors.append(image.pixelColor(20, 16) if kind == "line" else image.pixelColor(60, 40))
        assert selected_colors == [QColor("#ff0000") if kind == "line" else QColor("#00ff00")] * 2
        panel._copy_selection()
        panel._paste_selection()
        pasted = json.loads(lab.read_text())["annotations"][1]
        assert pasted["stroke_color"] == saved["stroke_color"]
        panel.undo()
        def reset(dialog):
            dialog._reset_appearance()
            return QDialog.DialogCode.Accepted
        monkeypatch.setattr(AnnotationEditor, "exec", reset)
        panel._edit_annotation(saved)
        assert json.loads(lab.read_text())["annotations"][0] == current
    finally:
        panel.close()
