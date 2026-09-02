from __future__ import annotations

from PyQt6.QtGui import QPainter

from .base import NullInputMixin, lamp
from ...wiring import PeripheralInstance

DEFAULT_COLORS = {"red": "#ef4444", "yellow": "#facc15", "green": "#22c55e"}


class TrafficLightRenderer(NullInputMixin):
    def size(self, peripheral: PeripheralInstance) -> tuple[int, int]:
        return (120, 180)

    def paint(self, painter: QPainter, rect, peripheral: PeripheralInstance, state) -> None:
        colors = {**DEFAULT_COLORS, **dict(peripheral.properties.get("colors", {}))}
        active = state.get("active", {})
        for y, terminal in ((58, "red"), (102, "yellow"), (146, "green")):
            lamp(painter, 60, y, bool(active.get(terminal, False)), colors[terminal])
