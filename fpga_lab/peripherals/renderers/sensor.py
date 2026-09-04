from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPainter

from ...i18n import t
from ...wiring import PeripheralInstance


class SensorRenderer:
    def size(self, peripheral: PeripheralInstance) -> tuple[int, int]:
        return (150, 88)

    def paint(self, painter: QPainter, rect, peripheral: PeripheralInstance, state) -> None:
        value = bool(state.get("sensor_value"))
        painter.setPen(QColor("#f8fafc") if value else QColor("#94a3b8"))
        label = t("Sensor: 1") if value else t("Sensor: 0")
        painter.drawText(rect.adjusted(10, 29, -8, -8), Qt.AlignmentFlag.AlignCenter, label)

    def mouse_press(self, peripheral, pos, input_changed) -> None:
        return

    def mouse_release(self, peripheral, pos, input_changed) -> None:
        return
