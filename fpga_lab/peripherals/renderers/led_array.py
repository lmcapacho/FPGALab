"""Reusable declarative renderer for LED bars and indicator arrays."""

from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen

from .base import NullInputMixin, lamp
from ...theme import color as theme_color
from ...wiring import PeripheralInstance


class LedArrayRenderer(NullInputMixin):
    """Draw any fixed terminal list described entirely by manifest metadata."""

    def __init__(self, visual: dict[str, object]):
        self._visual = dict(visual)
        self._terminals = tuple(str(name) for name in self._visual["terminals"])
        self._orientation = str(self._visual.get("orientation", "horizontal"))
        self._indicator_shape = str(self._visual.get("indicator_shape", "circle"))
        self._show_labels = bool(self._visual.get("show_labels", True))
        self._color_property = str(self._visual.get("color_property", "color"))
        self._size = tuple(int(value) for value in self._visual["size"])

    def size(self, peripheral: PeripheralInstance) -> tuple[int, int]:
        return self._size  # type: ignore[return-value]

    def paint(self, painter: QPainter, rect, peripheral: PeripheralInstance, state) -> None:
        brightness = state.get("brightness", state.get("active", {}))
        selected_color = str(peripheral.properties.get(self._color_property, "#ef4444"))
        width, height = self._size
        item_label_space = 24
        index_space = 14 if self._show_labels else 0
        content_height = height - item_label_space
        padding = 10
        usable_width = max(1, width - padding * 2)
        usable_height = max(1, content_height - padding * 2 - index_space)
        count = len(self._terminals)

        painter.save()
        painter.setPen(QPen(QColor("#020617"), 1.2))
        painter.setBrush(QColor("#090d14"))
        painter.drawRoundedRect(QRectF(2, 2, width - 4, content_height - 4), 8, 8)
        painter.setPen(theme_color("text_muted"))
        for index, terminal in enumerate(self._terminals):
            if self._orientation == "vertical":
                x = width / 2
                y = padding + usable_height * (index + 0.5) / count
            else:
                x = padding + usable_width * (index + 0.5) / count
                y = padding + usable_height / 2
            intensity = float(brightness.get(terminal, 0.0))
            if self._indicator_shape == "rectangle":
                self._paint_bar(painter, x, y, usable_width, usable_height, count, intensity, selected_color)
            else:
                lamp(painter, round(x), round(y), intensity, selected_color)
            if self._show_labels:
                painter.setPen(theme_color("text_muted"))
                label_rect = QRectF(x - 10, content_height - index_space - 2, 20, index_space)
                painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, str(index))
        painter.restore()

    def _paint_bar(
        self, painter: QPainter, x: float, y: float, usable_width: int, usable_height: int,
        count: int, brightness: float, selected_color: str,
    ) -> None:
        brightness = max(0.0, min(brightness, 1.0)) ** 0.38
        off = QColor("#2b1115")
        on = QColor(selected_color)
        fill = QColor(
            round(off.red() + (on.red() - off.red()) * brightness),
            round(off.green() + (on.green() - off.green()) * brightness),
            round(off.blue() + (on.blue() - off.blue()) * brightness),
        )
        if self._orientation == "vertical":
            bar_width = min(usable_width * 0.58, 38.0)
            bar_height = min(usable_height / count * 0.68, 18.0)
        else:
            bar_width = min(usable_width / count * 0.68, 18.0)
            bar_height = min(usable_height * 0.72, 38.0)
        bar = QRectF(x - bar_width / 2, y - bar_height / 2, bar_width, bar_height)
        painter.setPen(QPen(fill.lighter(125), 1.0))
        painter.setBrush(fill)
        painter.drawRoundedRect(bar, 2.5, 2.5)
        if brightness > 0.0:
            halo = QColor(on)
            halo.setAlpha(round(70 * brightness))
            painter.setPen(QPen(halo, 3.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(bar.adjusted(-1, -1, 1, 1), 3, 3)
