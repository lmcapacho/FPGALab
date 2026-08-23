"""Panel for registering peripherals and GPIO without visible wiring."""
from __future__ import annotations
import json
from pathlib import Path
from PyQt6.QtCore import QPointF, Qt, pyqtSignal
import re
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen
from PyQt6.QtWidgets import QComboBox, QColorDialog, QDialog, QDialogButtonBox, QFormLayout, QFrame, QGraphicsItem, QGraphicsRectItem, QGraphicsScene, QGraphicsView, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
from .board import BoardDefinition
from .constraints import PcfParser
from .i18n import language_manager, t
from .wiring import PERIPHERAL_LABELS, PERIPHERAL_TERMINALS, PeripheralInstance, VirtualLabProject


TRAFFIC_LIGHT_DEFAULT_COLORS = {"red": "#ef4444", "yellow": "#facc15", "green": "#22c55e"}

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
            segment.setStyleSheet("color:#475569; font: bold 12px monospace;")
            grid.addWidget(segment, row, column)
            self._segments[name] = segment

    def set_segment(self, name, active):
        segment = self._segments.get(name)
        if segment is not None:
            segment.setStyleSheet("color:#ff9d26; font: bold 12px monospace;" if active else "color:#475569; font: bold 12px monospace;")


class PeripheralConfigDialog(QDialog):
    """Modal editor for one instance; it does not render wires."""

    def __init__(self, peripheral, board, assigned_endpoints=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("Configure · {identifier}", identifier=peripheral.peripheral_id))
        self._board = board; self._assigned_endpoints = assigned_endpoints
        self._kind = peripheral.kind
        self._pickers = {}
        self._properties = dict(peripheral.properties)
        self._color = str(peripheral.properties.get("color", "#b6ff00"))
        self._traffic_colors = {
            **TRAFFIC_LIGHT_DEFAULT_COLORS,
            **dict(peripheral.properties.get("colors", {})),
        }
        self._traffic_color_buttons: dict[str, QPushButton] = {}
        self._delete_requested = False
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.identifier = QLineEdit(peripheral.peripheral_id)
        form.addRow(t("Identifier"), self.identifier)
        for terminal, direction in PERIPHERAL_TERMINALS[peripheral.kind].items():
            picker = QComboBox(); picker.addItem(t("— not connected —"), "")
            for pin in board.available_endpoints(direction):
                if pin.location.startswith("header") and (self._assigned_endpoints is None or pin.id in self._assigned_endpoints):
                    picker.addItem(pin.id, pin.id)
            index = picker.findData(peripheral.connections.get(terminal, ""))
            picker.setCurrentIndex(max(0, index))
            form.addRow(terminal, picker); self._pickers[terminal] = picker
        self.common = QComboBox(); self.common.addItems(["cathode", "anode"])
        self.common.setCurrentText(str(peripheral.properties.get("common", "cathode")))
        if peripheral.kind == "seven_segment": form.addRow(t("Common"), self.common)
        self.color = QPushButton(self._color)
        self.color.clicked.connect(self._choose_color)
        if peripheral.kind == "led":
            form.addRow(t("Color"), self.color)
        elif peripheral.kind == "traffic_light":
            for terminal in ("red", "yellow", "green"):
                button = QPushButton(self._traffic_colors[terminal])
                button.clicked.connect(lambda _checked=False, name=terminal: self._choose_color(name))
                self._traffic_color_buttons[terminal] = button
                form.addRow(terminal.capitalize(), button)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(t("Save"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(t("Cancel"))
        delete = buttons.addButton(t("Delete"), QDialogButtonBox.ButtonRole.DestructiveRole)
        delete.clicked.connect(self._request_delete)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)

    def _request_delete(self):
        self._delete_requested = True; self.done(2)

    def _choose_color(self, terminal: str | None = None):
        current = self._traffic_colors[terminal] if terminal else self._color
        color = QColorDialog.getColor(QColor(current), self)
        if not color.isValid():
            return
        if terminal:
            self._traffic_colors[terminal] = color.name()
            self._traffic_color_buttons[terminal].setText(color.name())
            return
        self._color = color.name()
        self.color.setText(self._color)

    def value(self):
        connections = {name: picker.currentData() for name, picker in self._pickers.items() if picker.currentData()}
        properties = dict(self._properties)
        if self._kind == "seven_segment": properties["common"] = self.common.currentText()
        if self._kind == "led":
            properties["color"] = self._color
        if self._kind == "traffic_light":
            properties["colors"] = self._traffic_colors
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
    """Scroll-free canvas whose logical size follows the available space."""

    def __init__(self, scene, delete_selected, parent=None):
        super().__init__(scene, parent)
        self._delete_selected = delete_selected
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.scene().setSceneRect(0, 0, self.viewport().width(), self.viewport().height())

    def mousePressEvent(self, event):
        self.setFocus()
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() in {Qt.Key.Key_Delete, Qt.Key.Key_Backspace}:
            selected = [item for item in self.scene().selectedItems() if isinstance(item, WorkbenchPeripheralItem)]
            if selected:
                self._delete_selected(selected[0].peripheral)
                event.accept()
                return
        super().keyPressEvent(event)



class WorkbenchPeripheralItem(QGraphicsRectItem):
    """Draggable item whose coordinates live in ``properties.position``."""

    def __init__(self, peripheral, configured, moved, input_changed):
        sizes = {"led": (120, 88), "traffic_light": (120, 180), "seven_segment": (150, 205), "button": (150, 88), "sensor": (150, 88)}
        width, height = sizes.get(peripheral.kind, (150, 88))
        super().__init__(0, 0, width, height)
        self._peripheral, self._configured, self._moved, self._input_changed = peripheral, configured, moved, input_changed
        position = peripheral.properties.get("position", [16, 16])
        self.setPos(float(position[0]), float(position[1]))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._active = {}; self._pressed = False; self._sensor_value = False; self._editable = True
        self._drag_dirty = False; self._last_position = self.pos()

    @property
    def peripheral(self):
        """Expose the selected model instance to the workbench keyboard handler."""
        return self._peripheral

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene() is not None:
            bounds = self.scene().sceneRect(); rect = self.rect()
            return QPointF(max(bounds.left(), min(value.x(), bounds.right() - rect.width())), max(bounds.top(), min(value.y(), bounds.bottom() - rect.height())))
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self._editable:
            self._last_position = value; self._drag_dirty = True
        return super().itemChange(change, value)

    def clamp_to_scene(self):
        if self.scene() is None: return
        bounds = self.scene().sceneRect(); rect = self.rect(); pos = self.pos()
        self.setPos(max(bounds.left(), min(pos.x(), bounds.right() - rect.width())), max(bounds.top(), min(pos.y(), bounds.bottom() - rect.height())))

    def _persist_position(self):
        if self._drag_dirty:
            self._moved(self._peripheral.peripheral_id, self._last_position.x(), self._last_position.y())
            self._drag_dirty = False

    def set_terminal(self, terminal, active):
        self._active[terminal] = active; self.update()

    def set_editable(self, enabled):
        self._editable = enabled
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, enabled)
        self.setCursor(Qt.CursorShape.OpenHandCursor if enabled else Qt.CursorShape.ArrowCursor)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#64748b") if not self.isSelected() else QColor("#38bdf8"), 2))
        painter.setBrush(QBrush(QColor("#172033")))
        painter.drawRoundedRect(self.rect(), 10, 10)
        painter.setPen(QColor("#e2e8f0")); painter.drawText(self.rect().adjusted(10, 7, -8, -42), Qt.AlignmentFlag.AlignLeft, self._peripheral.peripheral_id)
        kind = self._peripheral.kind
        if kind == "led":
            self._lamp(painter, 77, 47, self._active.get("anode", False), self._peripheral.properties.get("color", "#b6ff00"))
        elif kind == "traffic_light":
            colors = {**TRAFFIC_LIGHT_DEFAULT_COLORS, **dict(self._peripheral.properties.get("colors", {}))}
            for y, terminal in ((58, "red"), (102, "yellow"), (146, "green")):
                self._lamp(painter, 60, y, self._active.get(terminal, False), colors[terminal])
        elif kind == "seven_segment":
            self._draw_display(painter)
        else:
            state = self._pressed if kind == "button" else self._sensor_value
            painter.setPen(QColor("#f8fafc") if state else QColor("#94a3b8"))
            label = (t("Button: 1") if state else t("Button: 0")) if kind == "button" else (t("Sensor: 1") if state else t("Sensor: 0"))
            painter.drawText(self.rect().adjusted(10, 29, -8, -8), Qt.AlignmentFlag.AlignCenter, label)

    def _draw_display(self, painter):
        segments = {
            "a": ((48, 52), (102, 52)), "b": ((108, 58), (108, 98)), "c": ((108, 110), (108, 150)),
            "d": ((48, 156), (102, 156)), "e": ((42, 110), (42, 150)), "f": ((42, 58), (42, 98)), "g": ((48, 104), (102, 104)),
        }
        for terminal, (start, end) in segments.items():
            painter.setPen(QPen(QColor("#f97316") if self._active.get(terminal, False) else QColor("#334155"), 9, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(*start, *end)

    def _lamp(self, painter, x, y, active, color):
        painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(QColor(color) if active else QColor("#334155"))
        painter.drawEllipse(x - 10, y - 10, 20, 20)

    def mousePressEvent(self, event):
        if self._peripheral.kind == "button":
            self._pressed = True; self._input_changed(self._peripheral.peripheral_id, "signal", 1); self.update()
        elif self._peripheral.kind == "sensor":
            self._sensor_value = not self._sensor_value; self._input_changed(self._peripheral.peripheral_id, "signal", int(self._sensor_value)); self.update()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self._editable: self._configured(self._peripheral)
        event.accept()

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if self._peripheral.kind == "button": self._pressed = False; self._input_changed(self._peripheral.peripheral_id, "signal", 0); self.update()
        if self._editable:
            self._persist_position()


class PeripheralsPanel(QWidget):
    changed = pyqtSignal(str)
    input_changed = pyqtSignal(str, int)
    def __init__(self, board: BoardDefinition, pcf: Path | None, lab: Path, input_widths: dict[str, int] | None = None, parent=None):
        super().__init__(parent); self._board, self._pcf, self._lab = board, pcf, lab
        self._input_widths = input_widths or {}; self._input_values = {}; self._editing_enabled = True
        self._assigned_endpoints = None  # The entire board is available; the design PCF is optional.
        layout = QVBoxLayout(self); self._catalog_title = QLabel(); layout.addWidget(self._catalog_title)
        catalog = QHBoxLayout(); self.kind = QComboBox()
        for key, label in PERIPHERAL_LABELS.items(): self.kind.addItem(t(label), key)
        self._add_button = QPushButton(); self._add_button.clicked.connect(self._add)
        catalog.addWidget(self.kind); catalog.addWidget(self._add_button); layout.addLayout(catalog)
        self.status = QLabel(); layout.addWidget(self.status)
        self._workbench_hint = QLabel(); layout.addWidget(self._workbench_hint)
        self._connection_status = QLabel()
        self._connection_status.setStyleSheet("color:#93c5fd; font-size:11px;")
        layout.addWidget(self._connection_status)
        self._workbench_scene = QGraphicsScene(self); self._workbench_scene.setSceneRect(0, 0, 480, 420); self.workbench = WorkbenchView(self._workbench_scene, self._delete)
        self.workbench.setMinimumHeight(330); layout.addWidget(self.workbench, 1)
        self._workbench_bindings = {}; self._reload()
        language_manager.language_changed.connect(self._retranslate_ui)
        self._retranslate_ui()
    def _retranslate_ui(self) -> None:
        self._catalog_title.setText(t("Peripheral catalog"))
        for index in range(self.kind.count()):
            key = self.kind.itemData(index)
            self.kind.setItemText(index, t(PERIPHERAL_LABELS[key]))
        self._add_button.setText(t("＋ Add"))
        self.status.setText(t("Select a type and configure the part when creating it."))
        self._workbench_hint.setText(t("Virtual workbench · drag a part; double-click to configure or delete"))
        self._update_connection_status()
        for item in self._workbench_scene.items():
            item.update()

    def _constraints(self):
        """Load optional design constraints without requiring a PCF for the board UI."""
        return PcfParser.parse_file(self._pcf) if self._pcf and self._pcf.is_file() else []

    def _reload(self):
        project = VirtualLabProject.load(self._lab)
        wires = project.resolve(self._board, self._constraints())
        self._resolved_wires = wires
        self._connection_counts = (len(wires), sum(wire.hdl_net is not None for wire in wires))
        self._workbench_scene.clear(); self._workbench_bindings = {}
        for index, peripheral in enumerate(project.peripherals):
            bench_item = WorkbenchPeripheralItem(peripheral, self._configure, self._save_position, self._drive_input)
            bench_item.set_editable(self._editing_enabled)
            if "position" not in peripheral.properties:
                bench_item.setPos(16 + (index % 3) * 160, 16 + (index // 3) * 88)
            self._workbench_scene.addItem(bench_item)
            for wire in wires:
                if wire.peripheral_id == peripheral.peripheral_id:
                    self._workbench_bindings[(peripheral.peripheral_id, wire.terminal)] = (bench_item, wire.hdl_net)
        self._update_connection_status()

    def _update_connection_status(self) -> None:
        """Summarize physical terminals and the subset currently present in HDL."""
        total, mapped = getattr(self, "_connection_counts", (0, 0))
        if total == 0:
            self._connection_status.setText(t("Connection status: no peripheral terminals configured."))
            return
        unmapped = total - mapped
        if unmapped == 0:
            self._connection_status.setText(t(
                "Connection status: all {total} terminal(s) are mapped by the current PCF.",
                total=total,
            ))
            return
        self._connection_status.setText(t(
            "Connection status: {mapped}/{total} terminal(s) mapped; {unmapped} physically connected but unused by this HDL.",
            mapped=mapped,
            total=total,
            unmapped=unmapped,
        ))

    def set_editable(self, enabled):
        self._editing_enabled = enabled
        self.kind.setEnabled(enabled); self._add_button.setEnabled(enabled)
        for item in self._workbench_scene.items():
            if isinstance(item, WorkbenchPeripheralItem): item.set_editable(enabled)

    def open_connections(self) -> None:
        """Show PCF and peripheral mappings in a compact, inspectable table."""
        ConnectionDialog(self._board, self._constraints(), self._resolved_wires, self).exec()

    def _drive_input(self, peripheral_id, terminal, value):
        binding = self._workbench_bindings.get((peripheral_id, terminal))
        net = binding[1] if binding else None
        match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\[(\d+)\]", net or "")
        if not match or match.group(1) not in self._input_widths:
            self.status.setText(t("{identifier}: physically connected; the current HDL does not read this pin.", identifier=peripheral_id))
            return
        port, bit = match.group(1), int(match.group(2))
        if bit >= self._input_widths[port]: return
        current = self._input_values.get(port, 0)
        current = current | (1 << bit) if value else current & ~(1 << bit)
        self._input_values[port] = current; self.input_changed.emit(port, current)

    def _save_position(self, peripheral_id, x, y):
        raw = json.loads(self._lab.read_text(encoding="utf-8"))
        for item in raw.get("peripherals", []):
            if item["id"] == peripheral_id:
                item.setdefault("properties", {})["position"] = [round(x, 1), round(y, 1)]
                break
        self._lab.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")

    def _commit(self, raw, message):
        original = self._lab.read_text(encoding="utf-8")
        self._lab.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
        try:
            VirtualLabProject.load(self._lab).resolve(self._board, self._constraints())
        except Exception as exc:
            self._lab.write_text(original, encoding="utf-8")
            self._show_configuration_error(str(exc))
            return False
        self.status.setText(message); self._reload(); self.changed.emit(message); return True

    def _show_configuration_error(self, message: str) -> None:
        """Keep validation failures visible instead of hiding them below the catalog."""
        self.status.setText(message)
        QMessageBox.warning(self, t("Peripheral configuration"), message)

    def _configure(self, peripheral):
        dialog = PeripheralConfigDialog(peripheral, self._board, self._assigned_endpoints, self)
        result = dialog.exec()
        if result == 2: self._delete(peripheral); return
        if result != QDialog.DialogCode.Accepted: return
        value = dialog.value()
        if not value["id"] or len(value["connections"]) != len(PERIPHERAL_TERMINALS[peripheral.kind]):
            self._show_configuration_error(t("Complete the identifier and every terminal."))
            return
        raw = json.loads(self._lab.read_text(encoding="utf-8"))
        ids = [item["id"] for item in raw.get("peripherals", []) if item["id"] != peripheral.peripheral_id]
        if value["id"] in ids:
            self._show_configuration_error(t("A peripheral with that identifier already exists."))
            return
        for index, item in enumerate(raw.get("peripherals", [])):
            if item["id"] == peripheral.peripheral_id:
                dialog_properties = dict(value["properties"]); dialog_properties.pop("position", None)
                value["properties"] = {**item.get("properties", {}), **dialog_properties}
                raw["peripherals"][index] = value; break
        self._commit(raw, t("{identifier} updated", identifier=value["id"]))

    def _delete(self, peripheral):
        answer = QMessageBox.question(self, t("Delete peripheral"), t("Delete {identifier}?", identifier=peripheral.peripheral_id))
        if answer != QMessageBox.StandardButton.Yes: return
        raw = json.loads(self._lab.read_text(encoding="utf-8"))
        raw["peripherals"] = [item for item in raw.get("peripherals", []) if item["id"] != peripheral.peripheral_id]
        self._commit(raw, t("{identifier} deleted", identifier=peripheral.peripheral_id))

    def update_outputs(self, outputs: dict[str, int]) -> None:
        """Paint output peripherals from their actual HDL net resolved by the PCF."""
        for (_peripheral_id, terminal), (item, net) in self._workbench_bindings.items():
            match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_$]*)(?:\[(\d+)])?", net or "")
            if match is None:
                item.set_terminal(terminal, False)
                continue
            port, raw_bit = match.groups()
            bit = int(raw_bit) if raw_bit else 0
            item.set_terminal(terminal, bool(outputs.get(port, 0) & (1 << bit)))

    def _add(self):
        kind = self.kind.currentData()
        raw = json.loads(self._lab.read_text(encoding="utf-8"))
        existing = {item["id"] for item in raw.get("peripherals", [])}
        index = 1
        while f"{kind}_{index}" in existing: index += 1
        draft = PeripheralInstance(f"{kind}_{index}", kind, {}, {})
        dialog = PeripheralConfigDialog(draft, self._board, self._assigned_endpoints, self)
        if dialog.exec() != QDialog.DialogCode.Accepted: return
        value = dialog.value()
        if not value["id"] or len(value["connections"]) != len(PERIPHERAL_TERMINALS[kind]):
            self._show_configuration_error(t("Complete the identifier and every terminal."))
            return
        if value["id"] in existing:
            self._show_configuration_error(t("A peripheral with that identifier already exists."))
            return
        raw.setdefault("peripherals", []).append(value)
        self._commit(raw, t("{identifier} added", identifier=value["id"]))
