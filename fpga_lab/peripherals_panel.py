"""Panel sin cableado visual para registrar periféricos y GPIO."""
from __future__ import annotations
import json
from pathlib import Path
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QComboBox, QFormLayout, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget
from .board import BoardDefinition
from .constraints import PcfParser
from .wiring import VirtualLabProject

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


class PeripheralsPanel(QWidget):
    changed = pyqtSignal(str)
    def __init__(self, board: BoardDefinition, pcf: Path, lab: Path, parent=None):
        super().__init__(parent); self._board, self._pcf, self._lab = board, pcf, lab
        layout = QVBoxLayout(self); layout.addWidget(QLabel("Periféricos externos"))
        form = QFormLayout(); self.kind = QComboBox(); self.kind.addItems(["led", "button"])
        self.identifier = QLineEdit("led_externo_1"); self.pin = QComboBox()
        form.addRow("Tipo", self.kind); form.addRow("Id", self.identifier); form.addRow("GPIO", self.pin); layout.addLayout(form)
        self.kind.currentTextChanged.connect(self._refresh_pins); self._refresh_pins(self.kind.currentText())
        add = QPushButton("Agregar periférico"); add.clicked.connect(self._add); layout.addWidget(add)
        self.status = QLabel(""); layout.addWidget(self.status); self.items = QListWidget(); layout.addWidget(self.items); self._led_bindings = {}; self._segment_bindings = []; self._reload()
    def _refresh_pins(self, kind: str):
        direction = "output" if kind == "led" else "input"; self.pin.clear()
        self.pin.addItems(pin.id for pin in self._board.available_endpoints(direction) if pin.location.startswith("header"))
    def _reload(self):
        project = VirtualLabProject.load(self._lab); wires = project.resolve(self._board, PcfParser.parse_file(self._pcf))
        nets = {(wire.peripheral_id, wire.terminal): wire.hdl_net for wire in wires}
        self.items.clear(); self._led_bindings = {}; self._segment_bindings = []
        for peripheral in project.peripherals:
            card = QFrame(); row = QHBoxLayout(card); row.setContentsMargins(6, 4, 6, 4)
            if peripheral.kind == "led":
                visual = QLabel(); visual.setFixedSize(20, 20); visual.setStyleSheet("background:#334155; border-radius:10px; border:1px solid #64748b;")
                self._led_bindings[peripheral.peripheral_id] = (visual, nets.get((peripheral.peripheral_id, "anode"), ""))
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
            row.addWidget(QLabel(f"{peripheral.peripheral_id} · {next(iter(peripheral.connections.values()), "-")}")); row.addStretch()
            item = QListWidgetItem(); item.setSizeHint(card.sizeHint()); self.items.addItem(item); self.items.setItemWidget(item, card)

    def update_gpio(self, gpio_out: int):
        import re
        for visual, net in self._led_bindings.values():
            match = re.fullmatch(r"gpio_out\[(\d+)\]", net)
            on = bool(match and gpio_out & (1 << int(match.group(1))))
            visual.setStyleSheet("background:#b6ff00; border-radius:10px; border:1px solid #eaff7a;" if on else "background:#334155; border-radius:10px; border:1px solid #64748b;")
        for visual, terminal, net in self._segment_bindings:
            match = re.fullmatch(r"gpio_out\[(\d+)\]", net)
            visual.set_segment(terminal, bool(match and gpio_out & (1 << int(match.group(1)))))
    def _add(self):
        item_id, kind, endpoint = self.identifier.text().strip(), self.kind.currentText(), self.pin.currentText()
        if not item_id or not endpoint: self.status.setText("Indique id y GPIO."); return
        original = self._lab.read_text(encoding="utf-8"); raw = json.loads(original)
        raw.setdefault("peripherals", []).append({"id": item_id, "type": kind, "connections": {"anode" if kind == "led" else "signal": endpoint}})
        self._lab.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
        try:
            VirtualLabProject.load(self._lab).resolve(self._board, PcfParser.parse_file(self._pcf))
        except Exception as exc:
            self._lab.write_text(original, encoding="utf-8"); self.status.setText(str(exc)); return
        self.status.setText(f"{item_id} conectado a {endpoint}"); self._reload(); self.changed.emit(item_id)
