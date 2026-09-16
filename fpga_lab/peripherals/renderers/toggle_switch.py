"""Single-pole latching switch renderer and input behavior."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QPainter, QPen

from ...theme import color
from ...wiring import PeripheralInstance


class ToggleSwitchRenderer:
    """Keep one stable digital level and expose it through ``signal``."""

    def __init__(self) -> None:
        self._active = False

    def size(self, peripheral: PeripheralInstance) -> tuple[int, int]:
        return (96, 76)

    def paint(self, painter: QPainter, rect, peripheral: PeripheralInstance, state) -> None:
        painter.setPen(QPen(color("border_strong"), 1.5))
        painter.setBrush(QBrush(color("canvas")))
        painter.drawRoundedRect(18, 10, 60, 31, 15, 15)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color("success_surface") if self._active else color("surface_hover")))
        painter.drawRoundedRect(21, 13, 54, 25, 12, 12)
        knob_x = 53 if self._active else 23
        painter.setPen(QPen(color("success_hover") if self._active else color("border_strong"), 1.5))
        painter.setBrush(QBrush(color("success") if self._active else color("text_muted")))
        painter.drawEllipse(knob_x, 14, 23, 23)

    def mouse_press(self, peripheral, pos, input_changed) -> None:
        if 15 <= pos.x() <= 81 and 7 <= pos.y() <= 45:
            self._active = not self._active
            input_changed(peripheral.peripheral_id, "signal", int(self._active))

    def mouse_release(self, peripheral, pos, input_changed) -> None:
        return

    def sync_inputs(self, peripheral, input_changed) -> None:
        """Restore the latched level after the native simulation is reset."""
        input_changed(peripheral.peripheral_id, "signal", int(self._active))
