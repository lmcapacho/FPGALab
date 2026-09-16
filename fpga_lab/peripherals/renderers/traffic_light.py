from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QPainter, QPen

from .base import NullInputMixin, lamp
from ...theme import color
from ...wiring import PeripheralInstance

DEFAULT_COLORS = {"red": "#ef4444", "yellow": "#facc15", "green": "#22c55e"}


class TrafficLightRenderer(NullInputMixin):
    def size(self, peripheral: PeripheralInstance) -> tuple[int, int]:
        return (96, 170)

    def paint(self, painter: QPainter, rect, peripheral: PeripheralInstance, state) -> None:
        colors = {**DEFAULT_COLORS, **dict(peripheral.properties.get("colors", {}))}
        brightness = state.get("brightness", state.get("active", {}))
        painter.setPen(QPen(color("border_strong"), 1.5))
        painter.setBrush(QBrush(color("canvas")))
        painter.drawRoundedRect(18, 4, 60, 137, 9, 9)
        for y, terminal in ((29, "red"), (72, "yellow"), (115, "green")):
            # The upper half-ring suggests the visor found on a real signal.
            painter.setPen(QPen(color("surface_hover"), 6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawArc(28, y - 16, 40, 31, 0, 180 * 16)
            painter.setPen(QPen(color("border_strong"), 1.2))
            painter.setBrush(QBrush(color("segment_off")))
            painter.drawEllipse(34, y - 14, 28, 28)
            lamp(painter, 48, y, float(brightness.get(terminal, False)), colors[terminal])
