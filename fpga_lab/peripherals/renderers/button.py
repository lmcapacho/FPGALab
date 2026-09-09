from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPainter

from .base import NullInputMixin
from ...i18n import t
from ...theme import color
from ...wiring import PeripheralInstance


class ButtonRenderer(NullInputMixin):
    def size(self, peripheral: PeripheralInstance) -> tuple[int, int]:
        return (150, 88)

    def paint(self, painter: QPainter, rect, peripheral: PeripheralInstance, state) -> None:
        pressed = bool(state.get("pressed"))
        painter.setPen(color("text") if pressed else color("text_muted"))
        label = t("Button: 1") if pressed else t("Button: 0")
        painter.drawText(rect.adjusted(10, 29, -8, -8), Qt.AlignmentFlag.AlignCenter, label)
