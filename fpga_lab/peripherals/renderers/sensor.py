"""Photoelectric vehicle-presence sensor renderer."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen

from ...theme import color
from ...wiring import PeripheralInstance


class SensorRenderer:
    def size(self, peripheral: PeripheralInstance) -> tuple[int, int]:
        return (112, 84)

    def paint(self, painter: QPainter, rect, peripheral: PeripheralInstance, state) -> None:
        vehicle_present = bool(state.get("sensor_value"))
        painter.setPen(QPen(color("border_strong"), 1.5))
        painter.setBrush(QBrush(color("surface_hover")))
        painter.drawRoundedRect(11, 14, 20, 31, 5, 5)
        painter.drawRoundedRect(81, 14, 20, 31, 5, 5)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#991b1b")))
        painter.drawEllipse(17, 23, 8, 8)
        painter.setBrush(QBrush(QColor("#22c55e") if vehicle_present else QColor("#334155")))
        painter.drawEllipse(87, 23, 8, 8)

        painter.setPen(QPen(QColor("#fb7185"), 2, Qt.PenStyle.DashLine, Qt.PenCapStyle.RoundCap))
        if vehicle_present:
            painter.drawLine(31, 27, 43, 27)
            painter.drawLine(69, 27, 81, 27)
            _paint_vehicle(painter)
        else:
            painter.drawLine(31, 27, 81, 27)

    def mouse_press(self, peripheral, pos, input_changed) -> None:
        return

    def mouse_release(self, peripheral, pos, input_changed) -> None:
        return


def _paint_vehicle(painter: QPainter) -> None:
    """Draw a compact top view where the interrupted beam is unmistakable."""
    painter.setPen(QPen(QColor("#7dd3fc"), 1.5))
    painter.setBrush(QBrush(QColor("#0369a1")))
    painter.drawRoundedRect(42, 7, 28, 43, 8, 8)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(QColor("#bae6fd")))
    painter.drawRoundedRect(47, 13, 18, 10, 3, 3)
    painter.drawRoundedRect(47, 34, 18, 9, 3, 3)
    painter.setBrush(QBrush(QColor("#0f172a")))
    for x, y in ((39, 14), (68, 14), (39, 36), (68, 36)):
        painter.drawRoundedRect(x, y, 5, 9, 2, 2)
