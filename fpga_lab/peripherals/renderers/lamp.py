from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen, QRadialGradient

from .base import NullInputMixin
from ...theme import color as theme_color
from ...wiring import PeripheralInstance


class LampRenderer(NullInputMixin):
    def size(self, peripheral: PeripheralInstance) -> tuple[int, int]:
        return (72, 84)

    def paint(self, painter: QPainter, rect, peripheral: PeripheralInstance, state) -> None:
        brightness = float(state.get("brightness", {}).get("anode", state.get("active", {}).get("anode", False)))
        brightness = max(0.0, min(brightness, 1.0))
        selected = QColor(str(peripheral.properties.get("color", "#b6ff00")))
        center_x = 36

        if brightness > 0.01:
            halo = QRadialGradient(center_x, 31, 28)
            glow = QColor(selected)
            glow.setAlpha(round(105 * brightness))
            transparent = QColor(selected)
            transparent.setAlpha(0)
            halo.setColorAt(0.0, glow)
            halo.setColorAt(1.0, transparent)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(halo)
            painter.drawEllipse(8, 3, 56, 56)

        dome = QPainterPath()
        dome.moveTo(22, 43)
        dome.lineTo(22, 32)
        dome.cubicTo(22, 14, 50, 14, 50, 32)
        dome.lineTo(50, 43)
        dome.closeSubpath()
        off = selected.darker(360)
        edge = _blend(off, selected, brightness)
        highlight = _blend(off.lighter(135), selected.lighter(165), brightness)
        body = QRadialGradient(30, 23, 30)
        body.setColorAt(0.0, highlight)
        body.setColorAt(0.5, edge)
        body.setColorAt(1.0, edge.darker(150))
        painter.setPen(QPen(_blend(theme_color("border_strong"), selected, brightness * 0.7), 1.5))
        painter.setBrush(body)
        painter.drawPath(dome)

        painter.setPen(QPen(edge.darker(165), 1.2))
        painter.setBrush(edge.darker(125))
        painter.drawRoundedRect(19, 42, 34, 7, 2, 2)

        reflection = QColor("#ffffff")
        reflection.setAlpha(round(45 + 135 * brightness))
        painter.setPen(QPen(reflection, 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(26, 20, 18, 18, 75 * 16, 75 * 16)


def _blend(start: QColor, end: QColor, amount: float) -> QColor:
    amount = max(0.0, min(amount, 1.0))
    return QColor(
        round(start.red() + (end.red() - start.red()) * amount),
        round(start.green() + (end.green() - start.green()) * amount),
        round(start.blue() + (end.blue() - start.blue()) * amount),
    )
