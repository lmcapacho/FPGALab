"""Four-position DIP switch renderer and input behavior."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QFont, QPainter, QPen

from ...theme import color
from ...wiring import PeripheralInstance


class DipSwitchRenderer:
    """Keep four independent latching input states for one workbench item."""

    _CENTERS = (45, 82, 119, 156)

    def __init__(self) -> None:
        self._values = [False, False, False, False]

    def size(self, peripheral: PeripheralInstance) -> tuple[int, int]:
        return (200, 125)

    def values(self) -> tuple[bool, ...]:
        return tuple(self._values)

    def paint(self, painter: QPainter, rect, peripheral: PeripheralInstance, state) -> None:
        painter.setFont(QFont("Inter", 8, QFont.Weight.Bold))
        painter.setPen(color("text_muted"))
        painter.drawText(13, 60, "ON")
        for index, center in enumerate(self._CENTERS):
            painter.setPen(QPen(color("border_strong"), 1.5))
            painter.setBrush(QBrush(color("canvas")))
            painter.drawRoundedRect(center - 12, 43, 24, 52, 4, 4)
            active = self._values[index]
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(color("success") if active else color("text_muted")))
            painter.drawRoundedRect(center - 9, 47 if active else 72, 18, 19, 3, 3)
            painter.setPen(color("text"))
            painter.drawText(center - 3, 112, str(index + 1))

    def mouse_press(self, peripheral, pos, input_changed) -> None:
        if not 40 <= pos.y() <= 98:
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
