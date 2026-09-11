"""Panel for registering peripherals and GPIO without visible wiring."""
from __future__ import annotations
import copy
import json
from pathlib import Path
from PyQt6.QtCore import QPointF, QSize, QTimer, Qt, pyqtSignal
import re
from PyQt6.QtGui import QBrush, QColor, QFont, QKeySequence, QPainter, QPalette, QPen
from PyQt6.QtWidgets import QComboBox, QColorDialog, QDialog, QDialogButtonBox, QFormLayout, QFrame, QGraphicsItem, QGraphicsRectItem, QGraphicsScene, QGraphicsView, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QKeySequenceEdit, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
from .board import BoardDefinition
from .constraints import PcfParser
from .i18n import language_manager, t
from .peripheral_catalog_panel import PeripheralCatalogPanel
from .peripherals.catalog import load_catalog, spec_for
from .peripherals.manifest import RESERVED_PROPERTIES
from .peripherals.renderers import renderer_for
from .peripherals.renderers.vga_monitor import VgaMonitorRenderer
from .temporal import LedModel, SignalWindow
from .wiring import SUPPLY_ENDPOINTS, PeripheralInstance, VirtualLabProject
from .theme import color, style_button


_EXTERNAL_LIGHT_PERSISTENCE_SECONDS = 0.030
_VISUAL_FUSION_EDGE_RATE_HZ = 60.0

class SegmentDisplay(QFrame):
    """Compact representation of an external seven-segment display."""

    _POSITIONS = {"a": (0, 1), "b": (1, 2), "c": (3, 2), "d": (4, 1), "e": (3, 0), "f": (1, 0), "g": (2, 1)}

    def __init__(self, parent=None):
        super().__init__(parent)
        self._segments = {}
        grid = QGridLayout(self)
        grid.setContentsMargins(2, 2, 2, 2)
        grid.setSpacing(1)
        for name, (row, column) in self._POSITIONS.items():
            segment = QLabel("━" if name in {"a", "d", "g"} else "┃")
            segment.setAlignment(Qt.AlignmentFlag.AlignCenter)
            font = QFont("monospace", 12, QFont.Weight.Bold)
            segment.setFont(font)
            self._set_color(segment, color("segment_off"))
            grid.addWidget(segment, row, column)
            self._segments[name] = segment

    def set_segment(self, name, active):
        segment = self._segments.get(name)
        if segment is not None:
            self._set_color(segment, QColor("#ff9d26") if active else color("segment_off"))

    @staticmethod
    def _set_color(label: QLabel, value: QColor) -> None:
        label_palette = label.palette()
        label_palette.setColor(QPalette.ColorRole.WindowText, value)
        label.setPalette(label_palette)


class PeripheralConfigDialog(QDialog):
    """Modal editor for one instance; fields come from the catalog schema."""

    save_requested = pyqtSignal()

    def __init__(self, peripheral, board, assigned_endpoints=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("Configure · {identifier}", identifier=peripheral.peripheral_id))
        self._board = board
        self._assigned_endpoints = assigned_endpoints
        self._kind = peripheral.kind
        self._spec = spec_for(peripheral.kind)
        self._pickers = {}
        self._properties = dict(peripheral.properties)
        self._property_widgets = {}
        self._delete_requested = False
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.identifier = QLineEdit(peripheral.peripheral_id)
        form.addRow(t("Identifier"), self.identifier)
        for terminal in self._spec.terminals:
            picker = QComboBox()
            picker.addItem(t("— not connected —"), "")
            for supply in terminal.supplies:
                picker.addItem(t(f"{supply} (fixed)"), supply)
            for pin in board.available_endpoints(terminal.direction):
                if pin.location.startswith("header") and (self._assigned_endpoints is None or pin.id in self._assigned_endpoints):
                    picker.addItem(pin.id, pin.id)
            index = picker.findData(peripheral.connections.get(terminal.name, ""))
            picker.setCurrentIndex(max(0, index))
            label = terminal.name if terminal.required else f"{terminal.name} *"
            form.addRow(label, picker)
            self._pickers[terminal.name] = picker
        for name, schema in self._spec.properties.items():
            if name in RESERVED_PROPERTIES:
                continue
            form.addRow(t(str(schema.get("label", name))), self._property_widget(name, schema, peripheral.properties))
        layout.addLayout(form)
        self._error_label = QLabel()
        self._error_label.setObjectName("errorText")
        self._error_label.setWordWrap(True)
        self._error_label.setVisible(False)
        layout.addWidget(self._error_label)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(t("Save"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(t("Cancel"))
        delete = buttons.addButton(t("Delete"), QDialogButtonBox.ButtonRole.DestructiveRole)
        style_button(delete, "danger")
        style_button(buttons.button(QDialogButtonBox.StandardButton.Save), "primary")
        delete.clicked.connect(self._request_delete)
        buttons.accepted.connect(self.save_requested.emit)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _property_widget(self, name, schema, properties):
        kind = schema.get("type")
        if kind == "color":
            current = str(properties.get(name, schema.get("default", "#b6ff00")))
            button = QPushButton(current)
            button.clicked.connect(lambda _=False, key=name, widget=button: self._pick_color(key, widget, None))
            self._property_widgets[name] = ("color", button)
            return button
        if kind == "color_map":
            keys = list(schema.get("keys") or [])
            defaults = dict(schema.get("default") or {})
            current = {**defaults, **dict(properties.get(name, {}))}
            box = QWidget()
            row = QHBoxLayout(box)
            row.setContentsMargins(0, 0, 0, 0)
            buttons = {}
            for key in keys:
                button = QPushButton(str(current.get(key, "#ffffff")))
                button.clicked.connect(lambda _=False, map_name=name, map_key=key, widget=button: self._pick_color(map_name, widget, map_key))
                row.addWidget(QLabel(key))
                row.addWidget(button)
                buttons[key] = button
            self._property_widgets[name] = ("color_map", buttons, current)
            return box
        if kind == "enum":
            combo = QComboBox()
            for value in schema.get("values") or []:
                combo.addItem(str(value), str(value))
            current = str(properties.get(name, schema.get("default", "")))
            index = combo.findData(current)
            combo.setCurrentIndex(max(0, index))
            self._property_widgets[name] = ("enum", combo)
            return combo
        if kind == "boolean":
            from PyQt6.QtWidgets import QCheckBox
            box = QCheckBox()
            box.setChecked(bool(properties.get(name, schema.get("default", False))))
            self._property_widgets[name] = ("boolean", box)
            return box
        if kind == "key_sequence":
            editor = QKeySequenceEdit(self)
            editor.setKeySequence(QKeySequence(str(properties.get(name, schema.get("default", "")))))
            box = QWidget()
            row = QHBoxLayout(box)
            row.setContentsMargins(0, 0, 0, 0)
            row.addWidget(editor, 1)
            clear = QPushButton(t("Clear"))
            clear.clicked.connect(editor.clear)
            row.addWidget(clear)
            self._property_widgets[name] = ("key_sequence", editor)
            return box
        field = QLineEdit(str(properties.get(name, schema.get("default", ""))))
        self._property_widgets[name] = ("string", field)
        return field

    def _request_delete(self):
        self._delete_requested = True
        self.done(2)

    def show_error(self, message: str, endpoint: str | None = None) -> None:
        """Keep the editor open and clear only an invalid endpoint assignment."""
        if endpoint:
            for picker in self._pickers.values():
                if picker.currentData() == endpoint:
                    picker.setCurrentIndex(0)
                    break
        self._error_label.setText(message)
        self._error_label.setVisible(True)

    def _pick_color(self, property_name, button: QPushButton, map_key: str | None):
        current = button.text()
        color = QColorDialog.getColor(QColor(current), self)
        if not color.isValid():
            return
        button.setText(color.name())
        widget = self._property_widgets[property_name]
        if map_key is not None:
            widget[2][map_key] = color.name()

    def value(self):
        connections = {name: picker.currentData() for name, picker in self._pickers.items() if picker.currentData()}
        properties = dict(self._properties)
        for name, widget in self._property_widgets.items():
            kind = widget[0]
            if kind == "color":
                properties[name] = widget[1].text()
            elif kind == "color_map":
                properties[name] = dict(widget[2])
            elif kind == "enum":
                properties[name] = widget[1].currentData()
            elif kind == "boolean":
                properties[name] = widget[1].isChecked()
            elif kind == "key_sequence":
                properties[name] = widget[1].keySequence().toString(QKeySequence.SequenceFormat.PortableText)
            else:
                properties[name] = widget[1].text()
        return {"id": self.identifier.text().strip(), "type": self._kind, "connections": connections, "properties": properties}


class ConnectionDialog(QDialog):
    """Explain virtual physical connections without requiring visible wires."""

    def __init__(self, board: BoardDefinition, constraints, wires, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("Connections"))
        self.resize(780, 460)
        layout = QVBoxLayout(self)
        description = QLabel(t("Board endpoints used by the PCF or an external peripheral."))
        description.setWordWrap(True)
        layout.addWidget(description)
        table = QTableWidget(self)
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels([
            t("Board endpoint"),
            t("FPGA pin"),
            t("Direction"),
            t("HDL net (PCF)"),
            t("External peripheral"),
        ])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        net_by_pin = {constraint.fpga_pin: constraint.net for constraint in constraints}
        peripherals_by_endpoint: dict[str, list[str]] = {}
        for wire in wires:
            peripherals_by_endpoint.setdefault(wire.board_endpoint, []).append(f"{wire.peripheral_id}.{wire.terminal}")
        rows = [
            pin for pin in board.pins
            if pin.fpga_pin in net_by_pin or pin.id in peripherals_by_endpoint
        ]
        table.setRowCount(len(rows))
        for row, pin in enumerate(rows):
            values = (
                pin.id,
                pin.fpga_pin,
                pin.direction,
                net_by_pin.get(pin.fpga_pin, t("— not mapped —")),
                ", ".join(peripherals_by_endpoint.get(pin.id, ())) or t("— none —"),
            )
            for column, value in enumerate(values):
                table.setItem(row, column, QTableWidgetItem(value))
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(table, 1)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        close.accepted.connect(self.accept)
        layout.addWidget(close)


class WorkbenchView(QGraphicsView):
    """Zoomable, pannable workbench canvas with keyboard editing actions."""

    zoom_changed = pyqtSignal(float)
    camera_changed = pyqtSignal(QPointF)
    _CANVAS_EXTENT = 100_000.0

    def __init__(self, scene, delete_selected, duplicate_selected, persist_positions, undo, redo, parent=None):
        super().__init__(scene, parent)
        self._delete_selected = delete_selected
        self._duplicate_selected = duplicate_selected
        self._persist_positions = persist_positions
        self._undo = undo
        self._redo = redo
        self._zoom = 1.0
        self._panning = False
        self._pan_paused = False
        self._pan_button = None
        self._pan_start = QPointF()
        self._pan_center = QPointF()
        self._editing_enabled = True
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.ensure_scene_fits()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.ensure_scene_fits()

    def ensure_scene_fits(self) -> None:
        """Maintain a large symmetric canvas without exposing scroll bars."""
        extent = self._CANVAS_EXTENT
        self.scene().setSceneRect(-extent, -extent, extent * 2, extent * 2)

    def camera_center(self) -> QPointF:
        """Return the scene coordinate currently centered in the viewport."""
        return self.mapToScene(self.viewport().rect().center())

    def restore_camera(self, center: QPointF | None = None) -> None:
        """Restore a saved camera or center the initial collection of parts."""
        if center is None:
            bounds = self.scene().itemsBoundingRect()
            center = bounds.center() if not bounds.isEmpty() else QPointF(0.0, 0.0)
        self.centerOn(center)

    def mousePressEvent(self, event):
        self.setFocus()
        if (
            self._editing_enabled
            and event.button() == Qt.MouseButton.LeftButton
            and event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        ):
            item = self.itemAt(event.position().toPoint())
            if isinstance(item, WorkbenchPeripheralItem):
                item.setSelected(not item.isSelected())
                event.accept()
                return
        wants_pan = event.button() == Qt.MouseButton.MiddleButton or (
            event.button() == Qt.MouseButton.LeftButton
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        )
        if wants_pan:
            self._panning = True
            self._pan_paused = False
            self._pan_button = event.button()
            self._pan_start = event.position()
            self._pan_center = self.camera_center()
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self._set_canvas_cursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._panning and event.button() == self._pan_button:
            self._panning = False
            self._pan_paused = False
            self._pan_button = None
            self.setDragMode(
                QGraphicsView.DragMode.RubberBandDrag
                if self._editing_enabled else QGraphicsView.DragMode.NoDrag
            )
            self._set_canvas_cursor(Qt.CursorShape.ArrowCursor)
            self.camera_changed.emit(self.camera_center())
            event.accept()
            return
        super().mouseReleaseEvent(event)
        if self._editing_enabled and event.button() == Qt.MouseButton.LeftButton:
            updates = [
                update
                for item in self.scene().items()
                if isinstance(item, WorkbenchPeripheralItem)
                if (update := item.take_position_update()) is not None
            ]
            if updates:
                self._persist_positions(updates)

    def _set_canvas_cursor(self, shape: Qt.CursorShape) -> None:
        """Keep the view and its viewport cursor synchronized."""
        self.setCursor(shape)
        self.viewport().setCursor(shape)

    def mouseMoveEvent(self, event):
        inside = self.viewport().rect().contains(event.position().toPoint())
        grabbed_item = self.scene().mouseGrabberItem()
        if not inside and (self._panning or isinstance(grabbed_item, WorkbenchPeripheralItem)):
            self._pan_paused = self._panning
            event.accept()
            return
        if self._panning:
            if self._pan_paused:
                self._pan_start = event.position()
                self._pan_center = self.camera_center()
                self._pan_paused = False
                event.accept()
                return
            delta = event.position() - self._pan_start
            self.centerOn(self._pan_center - QPointF(delta.x() / self._zoom, delta.y() / self._zoom))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def wheelEvent(self, event):
        """Use the wheel exclusively for cursor-centered canvas zoom."""
        delta = event.angleDelta().y() or event.angleDelta().x()
        steps = delta / 120
        if steps:
            self.set_zoom(self._zoom * (1.15 ** steps))
        event.accept()

    def set_zoom(self, zoom: float) -> None:
        """Apply bounded cursor-anchored zoom independently of canvas size."""
        zoom = max(0.1, min(float(zoom), 2.5))
        if abs(zoom - self._zoom) < 0.001:
            return
        self._zoom = zoom
        self.resetTransform()
        self.scale(self._zoom, self._zoom)
        self.zoom_changed.emit(self._zoom)
        self.camera_changed.emit(self.camera_center())

    def zoom_in(self) -> None:
        self.set_zoom(self._zoom * 1.15)

    def zoom_out(self) -> None:
        self.set_zoom(self._zoom / 1.15)

    def reset_zoom(self) -> None:
        self.set_zoom(1.0)

    def fit_contents(self) -> None:
        """Fit all workbench parts in the viewport using the regular persisted zoom."""
        bounds = self.scene().itemsBoundingRect()
        if bounds.isEmpty():
            self.reset_zoom()
            return
        margin = 24.0
        fitted = bounds.adjusted(-margin, -margin, margin, margin)
        viewport = self.viewport().size()
        if fitted.width() <= 0 or fitted.height() <= 0:
            return
        zoom = min(viewport.width() / fitted.width(), viewport.height() / fitted.height())
        self.set_zoom(zoom)
        self.centerOn(bounds.center())
        self.camera_changed.emit(self.camera_center())

    def set_editable(self, enabled: bool) -> None:
        """Allow navigation while blocking destructive keyboard actions."""
        self._editing_enabled = enabled
        if not self._panning:
            self.setDragMode(
                QGraphicsView.DragMode.RubberBandDrag
                if enabled else QGraphicsView.DragMode.NoDrag
            )

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_0 and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.reset_zoom()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Z and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self._redo()
            else:
                self._undo()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Y and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._redo()
            event.accept()
            return
        if (
            self._editing_enabled
            and event.key() == Qt.Key.Key_D
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            selected = [item for item in self.scene().selectedItems() if isinstance(item, WorkbenchPeripheralItem)]
            if selected:
                self._duplicate_selected([item.peripheral for item in selected])
                event.accept()
                return
        if self._editing_enabled and event.key() in {Qt.Key.Key_Delete, Qt.Key.Key_Backspace}:
            selected = [item for item in self.scene().selectedItems() if isinstance(item, WorkbenchPeripheralItem)]
            if selected:
                self._delete_selected([item.peripheral for item in selected])
                event.accept()
                return
        super().keyPressEvent(event)



class WorkbenchPeripheralItem(QGraphicsRectItem):
    """Draggable item whose coordinates live in ``properties.position``."""

    def __init__(self, peripheral, configured, moved, input_changed):
        spec = spec_for(peripheral.kind)
        self._renderer = renderer_for(spec.visual["renderer"])
        width, height = self._renderer.size(peripheral)
        super().__init__(0, 0, width, height)
        self._peripheral, self._configured, self._moved, self._input_changed = peripheral, configured, moved, input_changed
        position = peripheral.properties.get("position", [16, 16])
        self.setPos(float(position[0]), float(position[1]))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self._active = {}
        self._brightness = {}
        self._pressed = False
        self._press_sources: set[str] = set()
        self._sensor_value = False
        self._editable = True
        self._snapshot = None
        self._drag_dirty = False
        self._last_position = self.pos()

    @property
    def peripheral(self):
        """Expose the selected model instance to the workbench keyboard handler."""
        return self._peripheral

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self._editable:
            self._last_position = value; self._drag_dirty = True
        return super().itemChange(change, value)

    def _persist_position(self):
        if self._drag_dirty:
            self._moved(self._peripheral.peripheral_id, self._last_position.x(), self._last_position.y())
            self._drag_dirty = False

    def take_position_update(self) -> tuple[str, float, float] | None:
        """Return one pending position and mark it persisted by the view batch."""
        if not self._drag_dirty:
            return None
        self._drag_dirty = False
        return self._peripheral.peripheral_id, self._last_position.x(), self._last_position.y()

    def set_terminal(self, terminal, active):
        self.set_terminal_brightness(terminal, 1.0 if active else 0.0)

    def set_terminal_brightness(self, terminal: str, brightness: float) -> None:
        """Expose a continuous brightness value to catalog renderers."""
        brightness = max(0.0, min(float(brightness), 1.0))
        self._brightness[terminal] = brightness ** 0.38
        self._active[terminal] = brightness > 0.0
        self.update()

    def set_snapshot(self, snapshot):
        self._snapshot = snapshot
        self.update()

    def drop_vga_images(self):
        if isinstance(self._renderer, VgaMonitorRenderer):
            self._renderer.drop_images()
            self._snapshot = None
            self.update()

    def set_editable(self, enabled):
        self._editable = enabled
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, enabled)
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def set_button_pressed(self, source: str, pressed: bool) -> None:
        """Merge mouse and keyboard press states for a momentary button."""
        if self._peripheral.kind != "button":
            return
        previous = self._pressed
        if pressed:
            self._press_sources.add(source)
        else:
            self._press_sources.discard(source)
        self._pressed = bool(self._press_sources)
        if self._pressed != previous:
            self._input_changed(self._peripheral.peripheral_id, "signal", int(self._pressed))
            self.update()

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        button_active = self._peripheral.kind == "button" and self._pressed
        border = color("success") if button_active else (
            color("border_strong") if not self.isSelected() else color("accent")
        )
        painter.setPen(QPen(border, 2))
        painter.setBrush(QBrush(color("success_surface") if button_active else color("surface_raised")))
        painter.drawRoundedRect(self.rect(), 10, 10)
        painter.setPen(color("text"))
        painter.drawText(self.rect().adjusted(10, 7, -8, -42), Qt.AlignmentFlag.AlignLeft, self._peripheral.peripheral_id)
        self._renderer.paint(painter, self.rect(), self._peripheral, {
            "active": self._active,
            "brightness": self._brightness,
            "pressed": self._pressed,
            "sensor_value": self._sensor_value,
            "snapshot": self._snapshot,
        })

    def mousePressEvent(self, event):
        if self._editable and event.button() == Qt.MouseButton.LeftButton:
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        if self._peripheral.kind == "sensor":
            self._sensor_value = not self._sensor_value
            self._input_changed(self._peripheral.peripheral_id, "signal", int(self._sensor_value))
            self.update()
        elif self._peripheral.kind == "button":
            self.set_button_pressed("mouse", True)
        self._renderer.mouse_press(self._peripheral, event.pos(), self._input_changed)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self._editable: self._configured(self._peripheral)
        event.accept()

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        if self._peripheral.kind == "button":
            self.set_button_pressed("mouse", False)
        self._renderer.mouse_release(self._peripheral, event.pos(), self._input_changed)


class PeripheralsPanel(QWidget):
    changed = pyqtSignal(str)
    input_changed = pyqtSignal(str, int)
    temporal_probes_changed = pyqtSignal(object)

    def __init__(
        self,
        board: BoardDefinition,
        pcf: Path | None,
        lab: Path,
        input_widths: dict[str, int] | None = None,
        output_widths: dict[str, int] | None = None,
        parent=None,
    ):
        super().__init__(parent); self._board, self._pcf, self._lab = board, pcf, lab
        self._input_widths = input_widths or {}
        self._output_widths = output_widths or {}
        self._output_indexes = {name: index for index, name in enumerate(self._output_widths)}
        self._input_values = {}; self._editing_enabled = True
        self._assigned_endpoints = None  # The entire board is available; the design PCF is optional.
        self._temporal_probes: list[tuple[tuple[int, int, bool], ...]] = []
        self._temporal_bindings: list[tuple[WorkbenchPeripheralItem, str]] = []
        self._temporal_terminals: set[tuple[str, str]] = set()
        self._temporal_models: list[LedModel] = []
        self._active_shortcut_keys: dict[int, list[WorkbenchPeripheralItem]] = {}
        self._restoring_workbench_state = False
        self._history: list[tuple[dict[str, object], dict[str, object], str]] = []
        self._history_index = 0
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 7, 8, 8)
        layout.setSpacing(5)
        workbench_header = QHBoxLayout(); workbench_header.setSpacing(4)
        self._workbench_hint = QLabel()
        workbench_header.addWidget(self._workbench_hint)
        self._connection_status = QLabel()
        self._connection_status.setObjectName("infoText")
        workbench_header.addWidget(self._connection_status)
        workbench_header.addStretch(1)
        self._zoom_out_button = QPushButton()
        self._zoom_reset_button = QPushButton()
        self._zoom_in_button = QPushButton()
        self._zoom_fit_button = QPushButton()
        self._undo_button = QPushButton()
        self._redo_button = QPushButton()
        style_button(self._undo_button, "icon", "undo")
        style_button(self._redo_button, "icon", "redo")
        style_button(self._zoom_out_button, "icon", "zoom-out")
        style_button(self._zoom_in_button, "icon", "zoom-in")
        style_button(self._zoom_fit_button, "icon", "fit")
        for button in (self._zoom_out_button, self._zoom_reset_button, self._zoom_in_button, self._zoom_fit_button):
            button.setFixedWidth(32)
        self._zoom_reset_button.setFixedWidth(60)
        workbench_header.addWidget(self._undo_button)
        workbench_header.addWidget(self._redo_button)
        workbench_header.addSpacing(4)
        workbench_header.addWidget(self._zoom_out_button)
        workbench_header.addWidget(self._zoom_reset_button)
        workbench_header.addWidget(self._zoom_in_button)
        workbench_header.addWidget(self._zoom_fit_button)
        layout.addLayout(workbench_header)
        self._workbench_scene = QGraphicsScene(self); self.workbench = WorkbenchView(self._workbench_scene, self._delete_many, self._duplicate_many, self._save_positions, self.undo, self.redo)
        self._undo_button.clicked.connect(self.undo)
        self._redo_button.clicked.connect(self.redo)
        self._zoom_out_button.clicked.connect(self.workbench.zoom_out)
        self._zoom_reset_button.clicked.connect(self.workbench.reset_zoom)
        self._zoom_in_button.clicked.connect(self.workbench.zoom_in)
        self._zoom_fit_button.clicked.connect(self.workbench.fit_contents)
        self.workbench.zoom_changed.connect(self._update_zoom_label)
        self.workbench.zoom_changed.connect(self._persist_workbench_zoom)
        self.workbench.camera_changed.connect(self._persist_workbench_center)
        self.workbench.setMinimumHeight(330); layout.addWidget(self.workbench, 1)
        self._catalog_button = QPushButton(self)
        self._catalog_button.setObjectName("floatingCatalogButton")
        style_button(self._catalog_button, "primary", "catalog")
        self._catalog_button.setFixedSize(44, 44)
        self._catalog_button.setIconSize(QSize(22, 22))
        self._catalog_button.clicked.connect(self._toggle_catalog)
        self._catalog_panel = PeripheralCatalogPanel(load_catalog(), self)
        self._catalog_panel.add_requested.connect(self._add_kind)
        self._workbench_bindings = {}; self._reload()
        self._update_history_actions()
        language_manager.language_changed.connect(self._retranslate_ui)
        self._retranslate_ui()
        QTimer.singleShot(0, self._position_catalog_button)
    def _retranslate_ui(self) -> None:
        self._catalog_button.setText("")
        self._catalog_button.setToolTip(t("Open peripheral catalog"))
        self._catalog_button.setAccessibleName(t("Open peripheral catalog"))
        self._catalog_panel.retranslate_ui()
        self._workbench_hint.setText(t("Virtual workbench"))
        self._workbench_hint.setToolTip(t("Drag empty space to select multiple parts. Shift+click changes the selection. Drag a selected part to move the group. Use the wheel to zoom. Ctrl+drag or middle-drag pans."))
        self._undo_button.setToolTip(t("Undo (Ctrl+Z)"))
        self._redo_button.setToolTip(t("Redo (Ctrl+Y or Ctrl+Shift+Z)"))
        self._zoom_out_button.setToolTip(t("Zoom out"))
        self._zoom_reset_button.setToolTip(t("Reset zoom"))
        self._zoom_in_button.setToolTip(t("Zoom in"))
        self._zoom_fit_button.setToolTip(t("Fit all parts"))
        self._update_zoom_label(self.workbench._zoom)
        self._update_connection_status()
        for item in self._workbench_scene.items():
            item.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "_catalog_panel"):
            self._catalog_panel.reposition()
        QTimer.singleShot(0, self._position_catalog_button)

    def _position_catalog_button(self) -> None:
        """Anchor the catalog action over the workbench's upper-right corner."""
        if not hasattr(self, "workbench") or not hasattr(self, "_catalog_button"):
            return
        margin = 14
        workbench_rect = self.workbench.geometry()
        x = workbench_rect.right() - self._catalog_button.width() - margin
        y = workbench_rect.top() + margin
        self._catalog_button.move(x, y)
        if not self._catalog_panel.isVisible():
            self._catalog_button.raise_()

    def _toggle_catalog(self) -> None:
        if self._editing_enabled:
            self._catalog_panel.toggle()

    def _constraints(self):
        """Load optional design constraints without requiring a PCF for the board UI."""
        return PcfParser.parse_file(self._pcf) if self._pcf and self._pcf.is_file() else []

    def set_lab_file(self, lab: str | Path) -> None:
        """Replace the workbench content with another saved laboratory."""
        next_lab = Path(lab)
        if next_lab == self._lab:
            return
        for port in tuple(self._input_values):
            self.input_changed.emit(port, 0)
        self._input_values.clear()
        self._active_shortcut_keys.clear()
        self._lab = next_lab
        self._history.clear()
        self._history_index = 0
        self._update_history_actions()
        self._reload()

    def _reload(self):
        project = VirtualLabProject.load(self._lab)
        wires = project.resolve(self._board, self._constraints())
        self._resolved_wires = wires
        self._connection_counts = (len(wires), sum(wire.hdl_net is not None for wire in wires))
        self._workbench_scene.clear(); self._workbench_bindings = {}
        workbench_items: dict[str, WorkbenchPeripheralItem] = {}
        for index, peripheral in enumerate(project.peripherals):
            bench_item = WorkbenchPeripheralItem(peripheral, self._configure, self._save_position, self._drive_input)
            bench_item.set_editable(self._editing_enabled)
            if "position" not in peripheral.properties:
                bench_item.setPos(16 + (index % 3) * 160, 16 + (index // 3) * 88)
            self._workbench_scene.addItem(bench_item)
            workbench_items[peripheral.peripheral_id] = bench_item
            for wire in wires:
                if wire.peripheral_id == peripheral.peripheral_id:
                    self._workbench_bindings[(peripheral.peripheral_id, wire.terminal)] = (bench_item, wire.hdl_net)
        self._rebuild_temporal_probes(project, workbench_items)
        self._restore_workbench_zoom()
        self._update_connection_status()

    def _restore_workbench_zoom(self) -> None:
        """Load optional presentation state while remaining compatible with older Labs."""
        try:
            raw = json.loads(self._lab.read_text(encoding="utf-8"))
            state = raw.get("workbench", {})
            zoom = float(state.get("zoom", 1.0)) if isinstance(state, dict) else 1.0
            raw_center = state.get("center") if isinstance(state, dict) else None
            center = (
                QPointF(float(raw_center[0]), float(raw_center[1]))
                if isinstance(raw_center, list) and len(raw_center) == 2
                else None
            )
        except (OSError, ValueError, json.JSONDecodeError):
            zoom = 1.0
            center = None
        self._restoring_workbench_state = True
        try:
            self.workbench.set_zoom(zoom)
            self.workbench.restore_camera(center)
        finally:
            self._restoring_workbench_state = False

    def _persist_workbench_zoom(self, zoom: float) -> None:
        """Store visual framing alongside the Lab rather than in global user preferences."""
        if self._restoring_workbench_state:
            return
        raw = json.loads(self._lab.read_text(encoding="utf-8"))
        state = raw.setdefault("workbench", {})
        if not isinstance(state, dict):
            state = raw["workbench"] = {}
        state["zoom"] = round(zoom, 4)
        self._lab.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")

    def _persist_workbench_center(self, center: QPointF) -> None:
        """Store the camera independently from peripheral coordinates."""
        if self._restoring_workbench_state:
            return
        raw = json.loads(self._lab.read_text(encoding="utf-8"))
        state = raw.setdefault("workbench", {})
        if not isinstance(state, dict):
            state = raw["workbench"] = {}
        state["center"] = [round(center.x(), 2), round(center.y(), 2)]
        self._lab.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")

    def _output_condition(self, net: str | None, expected: bool) -> tuple[int, int, bool] | None:
        match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_$]*)(?:\[(\d+)])?", net or "")
        if match is None:
            return None
        name, raw_bit = match.groups()
        bit = int(raw_bit) if raw_bit else 0
        if name not in self._output_widths or bit >= self._output_widths[name]:
            return None
        return self._output_indexes[name], bit, expected

    def _rebuild_temporal_probes(self, project, workbench_items) -> None:
        """Create output predicates from a peripheral's manifest metadata."""
        probes: list[tuple[tuple[int, int, bool], ...]] = []
        bindings: list[tuple[WorkbenchPeripheralItem, str]] = []
        temporal_terminals: set[tuple[str, str]] = set()

        def add(peripheral_id: str, terminal: str, conditions: list[tuple[int, int, bool]]) -> None:
            if conditions:
                probes.append(tuple(conditions))
                bindings.append((workbench_items[peripheral_id], terminal))

        for peripheral in project.peripherals:
            spec = spec_for(peripheral.kind)
            temporal = spec.temporal
            if temporal is None:
                continue
            if temporal["mode"] == "per_terminal":
                for terminal in spec.terminals:
                    if terminal.direction != "output":
                        continue
                    binding = self._workbench_bindings.get((peripheral.peripheral_id, terminal.name))
                    condition = self._output_condition(binding[1] if binding else None, True)
                    if condition is not None:
                        add(peripheral.peripheral_id, terminal.name, [condition])
                continue

            common_terminal = str(temporal["common_terminal"])
            common_type = str(peripheral.properties.get(str(temporal["polarity_property"]), "cathode"))
            common_endpoint = peripheral.connections.get(
                common_terminal, "GND" if common_type == "cathode" else "VCC"
            )
            if common_endpoint in SUPPLY_ENDPOINTS:
                common_conditions = [] if common_endpoint == ("GND" if common_type == "cathode" else "VCC") else None
            else:
                binding = self._workbench_bindings.get((peripheral.peripheral_id, common_terminal))
                condition = self._output_condition(binding[1] if binding else None, common_type == "anode")
                common_conditions = [condition] if condition is not None else None
            if common_conditions is None:
                temporal_terminals.update(
                    (peripheral.peripheral_id, str(terminal))
                    for terminal in temporal.get("active_terminals", ())
                )
                continue
            for terminal in temporal.get("active_terminals", ()):
                temporal_terminals.add((peripheral.peripheral_id, str(terminal)))
                binding = self._workbench_bindings.get((peripheral.peripheral_id, str(terminal)))
                # Segment current flows low for common-anode displays and high
                # for common-cathode displays. The common enable is handled above.
                condition = self._output_condition(binding[1] if binding else None, common_type == "cathode")
                if condition is not None:
                    add(peripheral.peripheral_id, str(terminal), [*common_conditions, condition])

        self._temporal_probes = probes
        self._temporal_bindings = bindings
        self._temporal_terminals = temporal_terminals | {
            (item.peripheral.peripheral_id, terminal) for item, terminal in bindings
        }
        self._temporal_models = [LedModel(_EXTERNAL_LIGHT_PERSISTENCE_SECONDS) for _ in bindings]
        self.temporal_probes_changed.emit(self.temporal_probes())

    def temporal_probes(self) -> list[tuple[tuple[int, int, bool], ...]]:
        return list(self._temporal_probes)

    def _update_connection_status(self) -> None:
        """Summarize physical terminals and the subset currently present in HDL."""
        total, mapped = getattr(self, "_connection_counts", (0, 0))
        if total == 0:
            self._connection_status.setText(t("PCF —"))
            self._connection_status.setToolTip(t("No peripheral terminals configured."))
            return
        unmapped = total - mapped
        self._connection_status.setText(t("PCF {mapped}/{total}", mapped=mapped, total=total))
        self._connection_status.setToolTip(t(
            "{mapped}/{total} peripheral terminal(s) are mapped by the current PCF; {unmapped} are physically connected but unused by this HDL.",
            mapped=mapped,
            total=total,
            unmapped=unmapped,
        ))

    def _update_zoom_label(self, zoom: float) -> None:
        self._zoom_reset_button.setText(f"{round(zoom * 100)}%")

    def _show_status(self, message: str, timeout_ms: int = 3500) -> None:
        """Forward concise feedback to the application's shared status bar."""
        del timeout_ms
        self.changed.emit(message)

    def set_editable(self, enabled):
        self._editing_enabled = enabled
        self._catalog_button.setEnabled(enabled)
        if not enabled:
            self._catalog_panel.close_drawer()
        self.workbench.set_editable(enabled)
        self._update_history_actions()
        for item in self._workbench_scene.items():
            if isinstance(item, WorkbenchPeripheralItem): item.set_editable(enabled)

    def handle_shortcut_event(self, event, pressed: bool) -> bool:
        """Route configured keyboard shortcuts as momentary external button presses."""
        key = event.key()
        if event.isAutoRepeat():
            return key in self._active_shortcut_keys
        if pressed:
            sequence = QKeySequence(event.keyCombination())
            matches: list[WorkbenchPeripheralItem] = []
            for item in self._workbench_scene.items():
                if not isinstance(item, WorkbenchPeripheralItem) or item.peripheral.kind != "button":
                    continue
                shortcut = str(item.peripheral.properties.get("shortcut", ""))
                configured = QKeySequence.fromString(shortcut, QKeySequence.SequenceFormat.PortableText)
                if shortcut and configured.matches(sequence) == QKeySequence.SequenceMatch.ExactMatch:
                    matches.append(item)
            if not matches:
                return False
            self._active_shortcut_keys[key] = matches
            for item in matches:
                item.set_button_pressed(f"key:{key}", True)
            return True
        matches = self._active_shortcut_keys.pop(key, [])
        for item in matches:
            item.set_button_pressed(f"key:{key}", False)
        return bool(matches)

    def open_connections(self) -> None:
        """Show PCF and peripheral mappings in a compact, inspectable table."""
        ConnectionDialog(self._board, self._constraints(), self._resolved_wires, self).exec()

    def _drive_input(self, peripheral_id, terminal, value):
        binding = self._workbench_bindings.get((peripheral_id, terminal))
        net = binding[1] if binding else None
        match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_$]*)(?:\[(\d+)\])?", net or "")
        if not match or match.group(1) not in self._input_widths:
            return
        port, raw_bit = match.groups()
        bit = int(raw_bit) if raw_bit else 0
        if bit >= self._input_widths[port]: return
        current = self._input_values.get(port, 0)
        current = current | (1 << bit) if value else current & ~(1 << bit)
        self._input_values[port] = current; self.input_changed.emit(port, current)

    def _save_position(self, peripheral_id, x, y):
        self._save_positions([(peripheral_id, x, y)])

    def _save_positions(self, updates: list[tuple[str, float, float]]) -> None:
        """Persist one completed drag as a single Lab document update."""
        raw = json.loads(self._lab.read_text(encoding="utf-8"))
        previous = json.loads(json.dumps(raw))
        positions = {
            peripheral_id: [round(x, 1), round(y, 1)]
            for peripheral_id, x, y in updates
        }
        for item in raw.get("peripherals", []):
            if item["id"] in positions:
                item.setdefault("properties", {})["position"] = positions[item["id"]]
        self._lab.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
        message = t("Moved {count} peripheral(s)", count=len(updates))
        self._record_history(previous, raw, message)
        self.changed.emit(message)

    def _commit(self, raw, message):
        previous = json.loads(self._lab.read_text(encoding="utf-8"))
        try:
            VirtualLabProject.from_raw(raw).resolve(self._board, self._constraints())
        except Exception as exc:
            self._show_configuration_error(str(exc))
            return False
        self._lab.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
        self._record_history(previous, raw, message)
        self._show_status(message)
        self._reload()
        return True

    def _record_history(self, before: dict[str, object], after: dict[str, object], message: str) -> None:
        """Record one complete Lab mutation, dropping any abandoned redo branch."""
        if before == after:
            return
        del self._history[self._history_index:]
        self._history.append((before, json.loads(json.dumps(after)), message))
        if len(self._history) > 50:
            del self._history[0]
        self._history_index = len(self._history)
        self._update_history_actions()

    def undo(self) -> None:
        if not self._editing_enabled or self._history_index == 0:
            return
        before, _, message = self._history[self._history_index - 1]
        self._history_index -= 1
        self._restore_history_document(before, t("Undid: {action}", action=message))

    def redo(self) -> None:
        if not self._editing_enabled or self._history_index >= len(self._history):
            return
        _, after, message = self._history[self._history_index]
        self._history_index += 1
        self._restore_history_document(after, t("Redid: {action}", action=message))

    def _restore_history_document(self, raw: dict[str, object], message: str) -> None:
        self._lab.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
        self._reload()
        self._show_status(message)
        self._update_history_actions()

    def _update_history_actions(self) -> None:
        if not hasattr(self, "_undo_button"):
            return
        self._undo_button.setEnabled(self._editing_enabled and self._history_index > 0)
        self._redo_button.setEnabled(self._editing_enabled and self._history_index < len(self._history))

    def history_state(self) -> tuple[list[tuple[dict[str, object], dict[str, object], str]], int]:
        """Return a detached session history before the simulation rebuilds the Lab widget."""
        return copy.deepcopy(self._history), self._history_index

    def restore_history_state(
        self,
        state: tuple[list[tuple[dict[str, object], dict[str, object], str]], int],
    ) -> None:
        """Restore history belonging to the same Lab after a widget replacement."""
        history, index = state
        self._history = copy.deepcopy(history[-50:])
        self._history_index = max(0, min(int(index), len(self._history)))
        self._update_history_actions()

    def _show_configuration_error(self, message: str) -> None:
        """Keep validation failures visible instead of hiding them below the catalog."""
        self._show_status(message, 7000)
        QMessageBox.warning(self, t("Peripheral configuration"), message)

    def _configure(self, peripheral):
        dialog = PeripheralConfigDialog(peripheral, self._board, self._assigned_endpoints, self)
        dialog.save_requested.connect(lambda: self._save_configuration(dialog, peripheral))
        result = dialog.exec()
        if result == 2: self._delete_many([peripheral]); return
        if result != QDialog.DialogCode.Accepted: return

    def _save_configuration(self, dialog: PeripheralConfigDialog, peripheral) -> None:
        value = dialog.value()
        required = spec_for(peripheral.kind).required_terminals(value["properties"])
        if not value["id"] or any(terminal not in value["connections"] for terminal in required):
            dialog.show_error(t("Complete the identifier and every terminal."))
            return
        raw = json.loads(self._lab.read_text(encoding="utf-8"))
        ids = [item["id"] for item in raw.get("peripherals", []) if item["id"] != peripheral.peripheral_id]
        if value["id"] in ids:
            dialog.show_error(t("A peripheral with that identifier already exists."))
            return
        for index, item in enumerate(raw.get("peripherals", [])):
            if item["id"] == peripheral.peripheral_id:
                dialog_properties = dict(value["properties"]); dialog_properties.pop("position", None)
                value["properties"] = {**item.get("properties", {}), **dialog_properties}
                raw["peripherals"][index] = value; break
        error = self._validation_error(raw)
        if error:
            dialog.show_error(error, self._conflicting_endpoint(error))
            return
        if self._commit(raw, t("{identifier} updated", identifier=value["id"])):
            dialog.accept()

    def _validation_error(self, raw) -> str | None:
        try:
            VirtualLabProject.from_raw(raw).resolve(self._board, self._constraints())
        except Exception as exc:
            return str(exc)
        return None

    @staticmethod
    def _conflicting_endpoint(error: str) -> str | None:
        marker = t("Input conflict: more than one peripheral drives {endpoint}.", endpoint="{endpoint}")
        pattern = re.escape(marker).replace(re.escape("{endpoint}"), r"(?P<endpoint>.+)")
        match = re.fullmatch(pattern, error)
        return match.group("endpoint") if match else None

    def _delete(self, peripheral):
        self._delete_many([peripheral])

    def _delete_many(self, peripherals) -> None:
        identifiers = {peripheral.peripheral_id for peripheral in peripherals}
        if not identifiers:
            return
        prompt = (
            t("Delete {identifier}?", identifier=next(iter(identifiers)))
            if len(identifiers) == 1
            else t("Delete {count} selected peripherals?", count=len(identifiers))
        )
        answer = QMessageBox.question(self, t("Delete peripheral"), prompt)
        if answer != QMessageBox.StandardButton.Yes: return
        raw = json.loads(self._lab.read_text(encoding="utf-8"))
        raw["peripherals"] = [item for item in raw.get("peripherals", []) if item["id"] not in identifiers]
        message = (
            t("{identifier} deleted", identifier=next(iter(identifiers)))
            if len(identifiers) == 1
            else t("{count} peripherals deleted", count=len(identifiers))
        )
        self._commit(raw, message)

    def _duplicate(self, peripheral) -> None:
        """Duplicate a selected visual part without copying electrical connections."""
        self._duplicate_many([peripheral])

    def _duplicate_many(self, peripherals) -> None:
        """Duplicate one selection in a single undoable Lab mutation."""
        if not self._editing_enabled:
            return
        raw = json.loads(self._lab.read_text(encoding="utf-8"))
        existing = {item["id"] for item in raw.get("peripherals", [])}
        duplicate_ids: list[str] = []
        for peripheral in peripherals:
            index = 1
            while f"{peripheral.kind}_{index}" in existing:
                index += 1
            identifier = f"{peripheral.kind}_{index}"
            existing.add(identifier)
            properties = dict(peripheral.properties)
            position = properties.get("position", [16, 16])
            properties["position"] = [round(float(position[0]) + 24, 1), round(float(position[1]) + 24, 1)]
            raw.setdefault("peripherals", []).append({
                "id": identifier,
                "type": peripheral.kind,
                "connections": {},
                "properties": properties,
            })
            duplicate_ids.append(identifier)
        message = (
            t("{identifier} duplicated", identifier=duplicate_ids[0])
            if len(duplicate_ids) == 1
            else t("{count} peripherals duplicated", count=len(duplicate_ids))
        )
        if duplicate_ids and self._commit(raw, message):
            for item in self._workbench_scene.items():
                if isinstance(item, WorkbenchPeripheralItem) and item.peripheral.peripheral_id in duplicate_ids:
                    item.setSelected(True)

    def update_outputs(self, outputs: dict[str, int]) -> None:
        """Paint output peripherals from their actual HDL net resolved by the PCF."""
        for (peripheral_id, terminal), (item, net) in self._workbench_bindings.items():
            if (peripheral_id, terminal) in self._temporal_terminals:
                continue
            match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_$]*)(?:\[(\d+)])?", net or "")
            if match is None:
                item.set_terminal(terminal, False)
                continue
            port, raw_bit = match.groups()
            bit = int(raw_bit) if raw_bit else 0
            item.set_terminal(terminal, bool(outputs.get(port, 0) & (1 << bit)))

    def update_frame(self, frame) -> None:
        self.update_outputs(frame.outputs)
        temporal = getattr(frame, "temporal", None)
        if temporal is not None:
            self._update_temporal_outputs(temporal)
        for item in self._workbench_scene.items():
            if not isinstance(item, WorkbenchPeripheralItem):
                continue
            snapshot = frame.sinks.get(item.peripheral.peripheral_id) if getattr(frame, "sinks", None) else None
            if snapshot is not None or isinstance(getattr(item, "_renderer", None), VgaMonitorRenderer):
                item.set_snapshot(snapshot)

    def _update_temporal_outputs(self, temporal) -> None:
        """Apply native duty-cycle summaries using the same visual persistence as board LEDs."""
        if temporal.samples <= 0:
            for item, terminal in self._temporal_bindings:
                item.set_terminal_brightness(terminal, 0.0)
            self._temporal_models = [LedModel(_EXTERNAL_LIGHT_PERSISTENCE_SECONDS) for _ in self._temporal_bindings]
            return
        for index, (item, terminal) in enumerate(self._temporal_bindings):
            model = self._temporal_models[index]
            edge_rate = temporal.edges[index] / temporal.elapsed_seconds if temporal.elapsed_seconds > 0 else 0.0
            final_level = bool(temporal.ends[index])
            high_samples = temporal.hits[index]
            if edge_rate < _VISUAL_FUSION_EDGE_RATE_HZ:
                high_samples = temporal.samples if final_level else 0
            window = SignalWindow(final_level, final_level, high_samples, temporal.samples, temporal.edges[index])
            item.set_terminal_brightness(terminal, model.advance({"anode": window}, temporal.elapsed_seconds))

    def drop_vga_images(self) -> None:
        for item in self._workbench_scene.items():
            if isinstance(item, WorkbenchPeripheralItem):
                item.drop_vga_images()

    def current_wires(self):
        return getattr(self, "_resolved_wires", ())

    def _add_kind(self, kind: str) -> None:
        if not self._editing_enabled or kind not in load_catalog():
            return
        self._catalog_panel.close_drawer()
        raw = json.loads(self._lab.read_text(encoding="utf-8"))
        existing = {item["id"] for item in raw.get("peripherals", [])}
        index = 1
        while f"{kind}_{index}" in existing: index += 1
        draft = PeripheralInstance(f"{kind}_{index}", kind, {}, {})
        dialog = PeripheralConfigDialog(draft, self._board, self._assigned_endpoints, self)
        dialog.save_requested.connect(lambda: self._save_new_peripheral(dialog, kind, existing))
        dialog.exec()

    def _save_new_peripheral(self, dialog: PeripheralConfigDialog, kind: str, existing: set[str]) -> None:
        value = dialog.value()
        required = spec_for(kind).required_terminals(value["properties"])
        if not value["id"] or any(terminal not in value["connections"] for terminal in required):
            dialog.show_error(t("Complete the identifier and every terminal."))
            return
        if value["id"] in existing:
            dialog.show_error(t("A peripheral with that identifier already exists."))
            return
        raw = json.loads(self._lab.read_text(encoding="utf-8"))
        raw.setdefault("peripherals", []).append(value)
        error = self._validation_error(raw)
        if error:
            dialog.show_error(error, self._conflicting_endpoint(error))
            return
        if self._commit(raw, t("{identifier} added", identifier=value["id"])):
            dialog.accept()
