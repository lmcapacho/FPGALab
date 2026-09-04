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
        brightness = state.get("brightness", state.get("active", {}))
        color = QColor(str(peripheral.properties.get("color", "#ff3b30")))
        for terminal, (start, end) in segments.items():
            intensity = float(brightness.get(terminal, False))
            painter.setPen(QPen(
                _blend(QColor("#334155"), color, intensity),
                9, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
            ))
            painter.drawLine(*start, *end)
            if intensity > 0.0:
                halo = QColor(color); halo.setAlpha(round(85 * intensity))
                painter.setPen(QPen(halo, 17, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                painter.drawLine(*start, *end)
                core = color.lighter(145); core.setAlpha(round(210 * intensity))
                painter.setPen(QPen(core, 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                painter.drawLine(*start, *end)


def _blend(off: QColor, on: QColor, brightness: float) -> QColor:
    return QColor(
        round(off.red() + (on.red() - off.red()) * brightness),
        round(off.green() + (on.green() - off.green()) * brightness),
        round(off.blue() + (on.blue() - off.blue()) * brightness),
    )
