"""Panel sin cableado visual para registrar periféricos y GPIO."""
from __future__ import annotations
import json
from pathlib import Path
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QComboBox, QFormLayout, QLabel, QLineEdit, QListWidget, QPushButton, QVBoxLayout, QWidget
from .board import BoardDefinition
from .constraints import PcfParser
from .wiring import VirtualLabProject

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
        self.status = QLabel(""); layout.addWidget(self.status); self.items = QListWidget(); layout.addWidget(self.items); self._reload()
    def _refresh_pins(self, kind: str):
        direction = "output" if kind == "led" else "input"; self.pin.clear()
        self.pin.addItems(pin.id for pin in self._board.available_endpoints(direction) if pin.location.startswith("header"))
    def _reload(self):
        project = VirtualLabProject.load(self._lab); self.items.clear()
        self.items.addItems(f"{p.peripheral_id} · {p.kind} · {next(iter(p.connections.values()), "-")}" for p in project.peripherals)
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
