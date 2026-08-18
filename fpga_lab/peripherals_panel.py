"""Panel sin cableado visual para registrar periféricos y GPIO."""
from __future__ import annotations
import json
from pathlib import Path
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen
from PyQt6.QtWidgets import QComboBox, QColorDialog, QDialog, QDialogButtonBox, QFormLayout, QFrame, QGraphicsItem, QGraphicsRectItem, QGraphicsScene, QGraphicsView, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout, QWidget
from .board import BoardDefinition
from .constraints import PcfParser
from .wiring import PERIPHERAL_LABELS, PERIPHERAL_TERMINALS, VirtualLabProject

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

    def __init__(self, peripheral, board, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Configurar · {peripheral.peripheral_id}")
        self._board = board
        self._kind = peripheral.kind
        self._pickers = {}
        self._color = str(peripheral.properties.get("color", "#b6ff00"))
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.identifier = QLineEdit(peripheral.peripheral_id)
        form.addRow("Identificador", self.identifier)
        for terminal, direction in PERIPHERAL_TERMINALS[peripheral.kind].items():
            picker = QComboBox(); picker.addItem("— sin conectar —", "")
            for pin in board.available_endpoints(direction):
                if pin.location.startswith("header"):
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
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)

    def _choose_color(self):
        color = QColorDialog.getColor(parent=self)
        if color.isValid(): self._color = color.name(); self.color.setText(self._color)

    def value(self):
        connections = {name: picker.currentData() for name, picker in self._pickers.items() if picker.currentData()}
        properties = {}
        if self._kind == "seven_segment": properties["common"] = self.common.currentText()
        if self._kind in {"led", "traffic_light"}: properties["color"] = self._color
        return {"id": self.identifier.text().strip(), "type": self._kind, "connections": connections, "properties": properties}


class WorkbenchPeripheralItem(QGraphicsRectItem):
    """Pieza arrastrable; sus coordenadas viven en properties.position."""

    def __init__(self, peripheral, configured, moved):
        super().__init__(0, 0, 154, 76)
        self._peripheral, self._configured, self._moved = peripheral, configured, moved
        position = peripheral.properties.get("position", [16, 16])
        self.setPos(float(position[0]), float(position[1]))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._active = {}

    def set_terminal(self, terminal, active):
        self._active[terminal] = active; self.update()

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
            for x, terminal, color in ((48, "red", "#ef4444"), (77, "yellow", "#facc15"), (106, "green", "#22c55e")):
                self._lamp(painter, x, 47, self._active.get(terminal, False), color)
        elif kind == "seven_segment":
            painter.setPen(QColor("#f97316")); painter.drawText(self.rect().adjusted(10, 29, -8, -8), Qt.AlignmentFlag.AlignCenter, "8")
        else:
            painter.setPen(QColor("#94a3b8")); painter.drawText(self.rect().adjusted(10, 29, -8, -8), Qt.AlignmentFlag.AlignCenter, "Pulsador" if kind == "button" else "Sensor 0/1")

    def _lamp(self, painter, x, y, active, color):
        painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(QColor(color) if active else QColor("#334155"))
        painter.drawEllipse(x - 10, y - 10, 20, 20)

    def mouseDoubleClickEvent(self, event):
        self._configured(self._peripheral); event.accept()

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self._moved(self._peripheral.peripheral_id, self.pos().x(), self.pos().y())


class PeripheralsPanel(QWidget):
    changed = pyqtSignal(str)
    def __init__(self, board: BoardDefinition, pcf: Path, lab: Path, parent=None):
        super().__init__(parent); self._board, self._pcf, self._lab = board, pcf, lab
        layout = QVBoxLayout(self); layout.addWidget(QLabel("Periféricos externos"))
        form = QFormLayout(); self.kind = QComboBox()
        for key, label in PERIPHERAL_LABELS.items(): self.kind.addItem(label, key)
        self.identifier = QLineEdit("led_externo_1"); self.common = QComboBox(); self.common.addItems(["cathode", "anode"])
        form.addRow("Tipo", self.kind); form.addRow("Id", self.identifier); form.addRow("Común display", self.common); layout.addLayout(form)
        self.connections_form = QFormLayout(); layout.addLayout(self.connections_form); self._connections = {}
        self.kind.currentIndexChanged.connect(self._refresh_pins); self._refresh_pins()
        add = QPushButton("Agregar periférico"); add.clicked.connect(self._add); layout.addWidget(add)
        self.status = QLabel(""); layout.addWidget(self.status)
        layout.addWidget(QLabel("Mesa virtual · arrastre una pieza; doble clic para configurar"))
        self._workbench_scene = QGraphicsScene(self); self.workbench = QGraphicsView(self._workbench_scene)
        self.workbench.setMinimumHeight(210); self.workbench.setSceneRect(0, 0, 480, 280); layout.addWidget(self.workbench)
        self.items = QListWidget(); layout.addWidget(self.items); self._led_bindings = {}; self._segment_bindings = []; self._workbench_bindings = {}; self._reload()
    def _refresh_pins(self):
        while self.connections_form.rowCount(): self.connections_form.removeRow(0)
        self._connections = {}
        kind = self.kind.currentData()
        for terminal, direction in PERIPHERAL_TERMINALS[kind].items():
            picker = QComboBox(); picker.addItem("— sin conectar —", "")
            for pin in self._board.available_endpoints(direction):
                if pin.location.startswith("header"): picker.addItem(pin.id, pin.id)
            self.connections_form.addRow(terminal, picker); self._connections[terminal] = picker
        self.common.setVisible(kind == "seven_segment")
    def _reload(self):
        project = VirtualLabProject.load(self._lab); wires = project.resolve(self._board, PcfParser.parse_file(self._pcf))
        nets = {(wire.peripheral_id, wire.terminal): wire.hdl_net for wire in wires}
        self.items.clear(); self._workbench_scene.clear(); self._led_bindings = {}; self._segment_bindings = []; self._workbench_bindings = {}
        for index, peripheral in enumerate(project.peripherals):
            card = QFrame(); row = QHBoxLayout(card); row.setContentsMargins(6, 4, 6, 4)
            if peripheral.kind == "led":
                visual = QLabel(); visual.setFixedSize(20, 20); visual.setStyleSheet("background:#334155; border-radius:10px; border:1px solid #64748b;")
                self._led_bindings[peripheral.peripheral_id] = (visual, nets.get((peripheral.peripheral_id, "anode"), ""), str(peripheral.properties.get("color", "#b6ff00")))
                row.addWidget(visual)
            elif peripheral.kind == "traffic_light":
                for terminal, color in (("red", "#ef4444"), ("yellow", "#facc15"), ("green", "#22c55e")):
                    visual = QLabel(); visual.setFixedSize(18, 18); visual.setStyleSheet("background:#334155; border-radius:9px; border:1px solid #64748b;")
                    self._led_bindings[f"{peripheral.peripheral_id}.{terminal}"] = (visual, nets.get((peripheral.peripheral_id, terminal), ""), color)
                    row.addWidget(visual)
            elif peripheral.kind == "button":
                visual = QPushButton("Pulsador"); visual.setEnabled(False); row.addWidget(visual)
            elif peripheral.kind == "seven_segment":
                visual = SegmentDisplay()
                for terminal in peripheral.connections:
                    self._segment_bindings.append((visual, terminal, nets.get((peripheral.peripheral_id, terminal), "")))
                row.addWidget(visual)
            else:
                visual = QLabel(peripheral.kind); row.addWidget(visual)
            detail = f"{len(peripheral.connections)}/7 segmentos" if peripheral.kind == "seven_segment" else next(iter(peripheral.connections.values()), "-")
            row.addWidget(QLabel(f"{peripheral.peripheral_id} · {detail}")); row.addStretch()
            configure = QPushButton("⚙"); configure.setToolTip("Configurar periférico")
            configure.clicked.connect(lambda _checked=False, p=peripheral: self._configure(p)); row.addWidget(configure)
            remove = QPushButton("×"); remove.setToolTip("Eliminar periférico")
            remove.clicked.connect(lambda _checked=False, p=peripheral: self._delete(p)); row.addWidget(remove)
            item = QListWidgetItem(); item.setSizeHint(card.sizeHint()); self.items.addItem(item); self.items.setItemWidget(item, card)
            bench_item = WorkbenchPeripheralItem(peripheral, self._configure, self._save_position)
            if "position" not in peripheral.properties: bench_item.setPos(16 + (index % 3) * 160, 16 + (index / 3) * 88)
            self._workbench_scene.addItem(bench_item)
            for terminal, net in ((wire.terminal, wire.hdl_net) for wire in wires if wire.peripheral_id == peripheral.peripheral_id):
                self._workbench_bindings[(peripheral.peripheral_id, terminal)] = (bench_item, net)

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
        dialog = PeripheralConfigDialog(peripheral, self._board, self)
        if not dialog.exec(): return
        value = dialog.value()
        if not value["id"] or len(value["connections"]) != len(PERIPHERAL_TERMINALS[peripheral.kind]):
            self.status.setText("Complete el identificador y todos los terminales."); return
        raw = json.loads(self._lab.read_text(encoding="utf-8"))
        ids = [item["id"] for item in raw.get("peripherals", []) if item["id"] != peripheral.peripheral_id]
        if value["id"] in ids: self.status.setText("Ya existe un periférico con ese identificador."); return
        for index, item in enumerate(raw.get("peripherals", [])):
            if item["id"] == peripheral.peripheral_id: raw["peripherals"][index] = value; break
        self._commit(raw, f"{value["id"]} actualizado")

    def _delete(self, peripheral):
        answer = QMessageBox.question(self, "Eliminar periférico", f"¿Eliminar {peripheral.peripheral_id}?")
        if answer != QMessageBox.StandardButton.Yes: return
        raw = json.loads(self._lab.read_text(encoding="utf-8"))
        raw["peripherals"] = [item for item in raw.get("peripherals", []) if item["id"] != peripheral.peripheral_id]
        self._commit(raw, f"{peripheral.peripheral_id} eliminado")

    def update_gpio(self, gpio_out: int):
        import re
        for visual, net, color in self._led_bindings.values():
            match = re.fullmatch(r"gpio_out\[(\d+)\]", net)
            on = bool(match and gpio_out & (1 << int(match.group(1))))
            visual.setStyleSheet(f"background:{color}; border-radius:10px; border:1px solid #ffffff;" if on else "background:#334155; border-radius:10px; border:1px solid #64748b;")
        for (peripheral_id, terminal), (item, net) in self._workbench_bindings.items():
            match = re.fullmatch(r"gpio_out\[(\d+)\]", net)
            item.set_terminal(terminal, bool(match and gpio_out & (1 << int(match.group(1)))))
        for visual, terminal, net in self._segment_bindings:
            match = re.fullmatch(r"gpio_out\[(\d+)\]", net)
            visual.set_segment(terminal, bool(match and gpio_out & (1 << int(match.group(1)))))
    def _add(self):
        item_id, kind = self.identifier.text().strip(), self.kind.currentData()
        connections = {terminal: picker.currentData() for terminal, picker in self._connections.items() if picker.currentData()}
        missing = set(self._connections) - set(connections)
        if not item_id or missing:
            self.status.setText("Asigne un GPIO a cada terminal: " + ", ".join(sorted(missing))); return
        original = self._lab.read_text(encoding="utf-8"); raw = json.loads(original)
        properties = {"common": self.common.currentText()} if kind == "seven_segment" else {}
        raw.setdefault("peripherals", []).append({"id": item_id, "type": kind, "connections": connections, "properties": properties})
        self._lab.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
        try:
            VirtualLabProject.load(self._lab).resolve(self._board, PcfParser.parse_file(self._pcf))
        except Exception as exc:
            self._lab.write_text(original, encoding="utf-8"); self.status.setText(str(exc)); return
        self.status.setText(f"{item_id}: {len(connections)} terminal(es) conectado(s)"); self._reload(); self.changed.emit(item_id)
