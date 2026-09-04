from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPainter, QPen

from .base import NullInputMixin
from ...wiring import PeripheralInstance


class SevenSegmentRenderer(NullInputMixin):
    def size(self, peripheral: PeripheralInstance) -> tuple[int, int]:
        return (150, 205)

    def paint(self, painter: QPainter, rect, peripheral: PeripheralInstance, state) -> None:
        segments = {
            "a": ((48, 52), (102, 52)), "b": ((108, 58), (108, 98)), "c": ((108, 110), (108, 150)),
            "d": ((48, 156), (102, 156)), "e": ((42, 110), (42, 150)), "f": ((42, 58), (42, 98)),
            "g": ((48, 104), (102, 104)),
        }
        active = state.get("active", {})
        for terminal, (start, end) in segments.items():
            painter.setPen(QPen(
                QColor("#f97316") if active.get(terminal, False) else QColor("#334155"),
                9, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
            ))
            painter.drawLine(*start, *end)
