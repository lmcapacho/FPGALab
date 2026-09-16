"""Four-position DIP switch renderer and input behavior."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QFont, QPainter, QPen

from ...theme import color
from ...wiring import PeripheralInstance


class DipSwitchRenderer:
    """Keep four independent latching input states for one workbench item."""

    _CENTERS = (39, 65, 91, 117)

    def __init__(self) -> None:
        self._values = [False, False, False, False]

    def size(self, peripheral: PeripheralInstance) -> tuple[int, int]:
        return (146, 90)

    def values(self) -> tuple[bool, ...]:
        return tuple(self._values)

    def paint(self, painter: QPainter, rect, peripheral: PeripheralInstance, state) -> None:
        painter.setFont(QFont("Inter", 8, QFont.Weight.Bold))
        painter.setPen(QPen(color("danger"), 1.5))
        painter.setBrush(QBrush(color("danger_surface")))
        painter.drawRoundedRect(7, 5, 132, 57, 6, 6)
        painter.setPen(color("text"))
        painter.drawText(11, 25, "ON")
        for index, center in enumerate(self._CENTERS):
            painter.setPen(QPen(color("border_strong"), 1.2))
            painter.setBrush(QBrush(color("canvas")))
            painter.drawRoundedRect(center - 9, 11, 18, 35, 3, 3)
            active = self._values[index]
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(color("success") if active else color("text_muted")))
            painter.drawRoundedRect(center - 6, 14 if active else 30, 12, 13, 2, 2)
            painter.setPen(color("text"))
            painter.drawText(center - 3, 58, str(index + 1))

    def mouse_press(self, peripheral, pos, input_changed) -> None:
        if not 8 <= pos.y() <= 50:
            return
        for index, center in enumerate(self._CENTERS):
            if abs(pos.x() - center) <= 14:
                self._values[index] = not self._values[index]
                input_changed(peripheral.peripheral_id, f"SW{index + 1}", int(self._values[index]))
                return

    def mouse_release(self, peripheral, pos, input_changed) -> None:
        return

    def sync_inputs(self, peripheral, input_changed) -> None:
        """Restore latched switch levels after the native model is reset."""
        for index, value in enumerate(self._values, start=1):
            input_changed(peripheral.peripheral_id, f"SW{index}", int(value))
