from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QPainter, QPen

from .base import NullInputMixin
from ...theme import color
from ...wiring import PeripheralInstance


class ButtonRenderer(NullInputMixin):
    def size(self, peripheral: PeripheralInstance) -> tuple[int, int]:
        return (92, 82)

    def paint(self, painter: QPainter, rect, peripheral: PeripheralInstance, state) -> None:
        pressed = bool(state.get("pressed"))
        # A tactile-switch silhouette remains recognizable at small workbench
        # zoom levels. The circular cap sinks and loses its shadow on press.
        painter.setPen(QPen(color("border_strong"), 1.5))
        painter.setBrush(QBrush(color("surface_hover")))
        painter.drawRoundedRect(25, 9, 42, 37, 7, 7)
        painter.setPen(QPen(color("canvas"), 3))
        painter.setBrush(QBrush(color("surface_raised")))
        painter.drawEllipse(31, 12, 30, 30)

        if not pressed:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(color("canvas")))
            painter.drawEllipse(34, 18, 25, 25)
        cap_size = 22 if pressed else 26
        cap_x = 46 - cap_size // 2
        cap_y = 26 - cap_size // 2 + (3 if pressed else 0)
        painter.setPen(QPen(color("success_hover") if pressed else color("accent_hover"), 1.5))
        painter.setBrush(QBrush(color("success") if pressed else color("accent")))
        painter.drawEllipse(cap_x, cap_y, cap_size, cap_size)
        painter.setPen(QPen(color("accent_text"), 1.4))
        painter.drawArc(cap_x + 5, cap_y + 4, cap_size - 10, 8, 25 * 16, 130 * 16)
