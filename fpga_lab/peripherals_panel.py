"""Panel sin cableado visual para registrar periféricos y GPIO."""
from __future__ import annotations
import json
from pathlib import Path
from PyQt6.QtCore import Qt, pyqtSignal
import re
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen
from PyQt6.QtWidgets import QComboBox, QColorDialog, QDialog, QDialogButtonBox, QFormLayout, QFrame, QGraphicsItem, QGraphicsRectItem, QGraphicsScene, QGraphicsView, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout, QWidget
from .board import BoardDefinition
from .constraints import PcfParser
from .wiring import PERIPHERAL_LABELS, PERIPHERAL_TERMINALS, PeripheralInstance, VirtualLabProject

class SegmentDisplay(QFrame):
    """Representacion compacta de un display externo de siete segmentos."""

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
    """Editor modal de una instancia; no representa cables."""

    def __init__(self, peripheral, board, assigned_endpoints=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Configurar · {peripheral.peripheral_id}")
        self._board = board; self._assigned_endpoints = assigned_endpoints
        self._kind = peripheral.kind
        self._pickers = {}
        self._properties = dict(peripheral.properties)
        self._color = str(peripheral.properties.get("color", "#b6ff00")); self._delete_requested = False
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.identifier = QLineEdit(peripheral.peripheral_id)
        form.addRow("Identificador", self.identifier)
        for terminal, direction in PERIPHERAL_TERMINALS[peripheral.kind].items():
            picker = QComboBox(); picker.addItem("— sin conectar —", "")
            for pin in board.available_endpoints(direction):
                if pin.location.startswith("header") and (self._assigned_endpoints is None or pin.id in self._assigned_endpoints):
                    picker.addItem(pin.id, pin.id)
            index = picker.findData(peripheral.connections.get(terminal, ""))
            picker.setCurrentIndex(max(0, index))
            form.addRow(terminal, picker); self._pickers[terminal] = picker
        self.common = QComboBox(); self.common.addItems(["cathode", "anode"])
        self.common.setCurrentText(str(peripheral.properties.get("common", "cathode")))
        if peripheral.kind == "seven_segment": form.addRow("Común", self.common)
        self.color = QPushButton(self._color)
        self.color.clicked.connect(self._choose_color)
        if peripheral.kind in {"led", "traffic_light"}: form.addRow("Color", self.color)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save)
        delete = buttons.addButton("Eliminar", QDialogButtonBox.ButtonRole.DestructiveRole)
        delete.clicked.connect(self._request_delete)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)

    def _request_delete(self):
        self._delete_requested = True; self.done(2)

    def _choose_color(self):
        color = QColorDialog.getColor(parent=self)
        if color.isValid(): self._color = color.name(); self.color.setText(self._color)

    def value(self):
        connections = {name: picker.currentData() for name, picker in self._pickers.items() if picker.currentData()}
        properties = dict(self._properties)
        if self._kind == "seven_segment": properties["common"] = self.common.currentText()
        if self._kind in {"led", "traffic_light"}: properties["color"] = self._color
        return {"id": self.identifier.text().strip(), "type": self._kind, "connections": connections, "properties": properties}


class WorkbenchPeripheralItem(QGraphicsRectItem):
    """Pieza arrastrable; sus coordenadas viven en properties.position."""

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

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self._editable:
            self._last_position = value; self._drag_dirty = True
        return super().itemChange(change, value)

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
            for y, terminal, color in ((58, "red", "#ef4444"), (102, "yellow", "#facc15"), (146, "green", "#22c55e")):
                self._lamp(painter, 60, y, self._active.get(terminal, False), color)
        elif kind == "seven_segment":
            self._draw_display(painter)
        else:
            state = self._pressed if kind == "button" else self._sensor_value
            painter.setPen(QColor("#f8fafc") if state else QColor("#94a3b8"))
            label = ("Pulsador: 1" if state else "Pulsador: 0") if kind == "button" else ("Sensor: 1" if state else "Sensor: 0")
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
    def __init__(self, board: BoardDefinition, pcf: Path, lab: Path, input_widths: dict[str, int] | None = None, parent=None):
        super().__init__(parent); self._board, self._pcf, self._lab = board, pcf, lab
        self._input_widths = input_widths or {}; self._input_values = {}; self._editing_enabled = True
        self._assigned_endpoints = None  # La placa completa está disponible; el PCF del diseño es opcional.
        layout = QVBoxLayout(self); layout.addWidget(QLabel("Catálogo de periféricos"))
        catalog = QHBoxLayout(); self.kind = QComboBox()
        for key, label in PERIPHERAL_LABELS.items(): self.kind.addItem(label, key)
        self._add_button = QPushButton("＋ Agregar"); self._add_button.clicked.connect(self._add)
        catalog.addWidget(self.kind); catalog.addWidget(self._add_button); layout.addLayout(catalog)
        self.status = QLabel("Seleccione un tipo y configure la pieza al crearla."); layout.addWidget(self.status)
        layout.addWidget(QLabel("Mesa virtual · arrastre una pieza; doble clic para configurar o eliminar"))
        self._workbench_scene = QGraphicsScene(self); self.workbench = QGraphicsView(self._workbench_scene)
        self.workbench.setMinimumHeight(330); self.workbench.setSceneRect(0, 0, 480, 420); layout.addWidget(self.workbench, 1)
        self._workbench_bindings = {}; self._reload()
    def _reload(self):
        project = VirtualLabProject.load(self._lab)
        wires = project.resolve(self._board, PcfParser.parse_file(self._pcf))
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

    def set_editable(self, enabled):
        self._editing_enabled = enabled
        self.kind.setEnabled(enabled); self._add_button.setEnabled(enabled)
        for item in self._workbench_scene.items():
            if isinstance(item, WorkbenchPeripheralItem): item.set_editable(enabled)

    def _drive_input(self, peripheral_id, terminal, value):
        binding = self._workbench_bindings.get((peripheral_id, terminal))
        net = binding[1] if binding else None
        match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\[(\d+)\]", net or "")
        if not match or match.group(1) not in self._input_widths:
            self.status.setText(f"{peripheral_id}: conectado físicamente; el HDL actual no lee este pin.")
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
            VirtualLabProject.load(self._lab).resolve(self._board, PcfParser.parse_file(self._pcf))
        except Exception as exc:
            self._lab.write_text(original, encoding="utf-8"); self.status.setText(str(exc)); return False
        self.status.setText(message); self._reload(); self.changed.emit(message); return True

    def _configure(self, peripheral):
        dialog = PeripheralConfigDialog(peripheral, self._board, self._assigned_endpoints, self)
        result = dialog.exec()
        if result == 2: self._delete(peripheral); return
        if result != QDialog.DialogCode.Accepted: return
        value = dialog.value()
        if not value["id"] or len(value["connections"]) != len(PERIPHERAL_TERMINALS[peripheral.kind]):
            self.status.setText("Complete el identificador y todos los terminales."); return
        raw = json.loads(self._lab.read_text(encoding="utf-8"))
        ids = [item["id"] for item in raw.get("peripherals", []) if item["id"] != peripheral.peripheral_id]
        if value["id"] in ids: self.status.setText("Ya existe un periférico con ese identificador."); return
        for index, item in enumerate(raw.get("peripherals", [])):
            if item["id"] == peripheral.peripheral_id:
                value["properties"] = {**item.get("properties", {}), **value["properties"]}
                raw["peripherals"][index] = value; break
        self._commit(raw, f"{value["id"]} actualizado")

    def _delete(self, peripheral):
        answer = QMessageBox.question(self, "Eliminar periférico", f"¿Eliminar {peripheral.peripheral_id}?")
        if answer != QMessageBox.StandardButton.Yes: return
        raw = json.loads(self._lab.read_text(encoding="utf-8"))
        raw["peripherals"] = [item for item in raw.get("peripherals", []) if item["id"] != peripheral.peripheral_id]
        self._commit(raw, f"{peripheral.peripheral_id} eliminado")

    def update_gpio(self, gpio_out: int):
        import re
        for (_peripheral_id, terminal), (item, net) in self._workbench_bindings.items():
            match = re.fullmatch(r"gpio_out\[(\d+)\]", net or "")
            item.set_terminal(terminal, bool(match and gpio_out & (1 << int(match.group(1)))))

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
            self.status.setText("Complete el identificador y todos los terminales."); return
        if value["id"] in existing:
            self.status.setText("Ya existe un periférico con ese identificador."); return
        raw.setdefault("peripherals", []).append(value)
        self._commit(raw, f"{value["id"]} agregado")
