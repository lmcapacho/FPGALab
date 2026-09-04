from __future__ import annotations

from PyQt6.QtGui import QPainter

from .base import NullInputMixin, lamp
from ...wiring import PeripheralInstance


class LampRenderer(NullInputMixin):
    def size(self, peripheral: PeripheralInstance) -> tuple[int, int]:
        return (120, 88)

    def paint(self, painter: QPainter, rect, peripheral: PeripheralInstance, state) -> None:
        active = bool(state.get("active", {}).get("anode", False))
        color = str(peripheral.properties.get("color", "#b6ff00"))
        lamp(painter, 77, 47, active, color)
