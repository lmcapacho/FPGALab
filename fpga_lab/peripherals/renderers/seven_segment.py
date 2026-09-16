from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPainter, QPen

from .base import NullInputMixin
from ...wiring import PeripheralInstance
from ...theme import color as theme_color


class SevenSegmentRenderer(NullInputMixin):
    def size(self, peripheral: PeripheralInstance) -> tuple[int, int]:
        return (138, 150)

    def paint(self, painter: QPainter, rect, peripheral: PeripheralInstance, state) -> None:
        brightness = state.get("brightness", state.get("active", {}))
        color = QColor(str(peripheral.properties.get("color", "#ff3b30")))
        painter.save()
        painter.translate(3, 0)
        painter.scale(0.88, 0.88)
        paint_seven_segments(painter, brightness, color, offset_y=-32)
        painter.restore()


def paint_seven_segments(
    painter: QPainter,
    brightness,
    color: QColor,
    *,
    offset_y: int = 0,
) -> None:
    """Paint the shared seven-segment geometry using continuous intensities."""
    segments = {
        "a": ((48, 52), (102, 52)), "b": ((108, 58), (108, 98)), "c": ((108, 110), (108, 150)),
        "d": ((48, 156), (102, 156)), "e": ((42, 110), (42, 150)), "f": ((42, 58), (42, 98)),
        "g": ((48, 104), (102, 104)),
    }
    for terminal, (start, end) in segments.items():
        intensity = float(brightness.get(terminal, False))
        painter.setPen(QPen(
            _blend(theme_color("segment_off"), color, intensity),
            9, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
        ))
        shifted_start = (start[0], start[1] + offset_y)
        shifted_end = (end[0], end[1] + offset_y)
        painter.drawLine(*shifted_start, *shifted_end)
        if intensity > 0.0:
            halo = QColor(color); halo.setAlpha(round(85 * intensity))
            painter.setPen(QPen(halo, 17, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(*shifted_start, *shifted_end)
            core = color.lighter(145); core.setAlpha(round(210 * intensity))
            painter.setPen(QPen(core, 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(*shifted_start, *shifted_end)


def _blend(off: QColor, on: QColor, brightness: float) -> QColor:
    return QColor(
        round(off.red() + (on.red() - off.red()) * brightness),
        round(off.green() + (on.green() - off.green()) * brightness),
        round(off.blue() + (on.blue() - off.blue()) * brightness),
    )
