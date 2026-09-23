"""Generic pulse-width-position renderer for no-code servo packages."""

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen

from ...theme import color as theme_color
from .base import NullInputMixin


def pulse_to_angle(pulse_seconds: float, min_us: float, max_us: float, min_angle: float, max_angle: float) -> float:
    """Map a completed high pulse to a bounded visual position."""
    fraction = max(0.0, min(1.0, (pulse_seconds * 1_000_000 - min_us) / (max_us - min_us)))
    return min_angle + fraction * (max_angle - min_angle)


class PulseServoRenderer(NullInputMixin):
    def __init__(self, visual: dict[str, object]):
        self._size = tuple(int(value) for value in visual["size"])
        self._terminal = str(visual["terminal"])
        self._min_us = float(visual["pulse_min_us"])
        self._max_us = float(visual["pulse_max_us"])
        self._min_angle = float(visual["angle_min_degrees"])
        self._max_angle = float(visual["angle_max_degrees"])
        self._color_property = str(visual.get("color_property", "color"))

    def size(self, peripheral) -> tuple[int, int]:
        return self._size  # type: ignore[return-value]

    def paint(self, painter: QPainter, rect, peripheral, state) -> None:
        del rect
        width, height = self._size
        observations = state.get("temporal", {})
        observation = observations.get(self._terminal) if isinstance(observations, dict) else None
        pulse = observation.get("pulse_high_seconds") if observation and state.get("powered") else None
        angle = (
            pulse_to_angle(float(pulse), self._min_us, self._max_us, self._min_angle, self._max_angle)
            if pulse is not None else (self._min_angle + self._max_angle) / 2
        )
        accent = QColor(str(peripheral.properties.get(self._color_property, "#38bdf8")))
        center_x, center_y = width / 2, (height - 24) / 2 + 12
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(theme_color("border_strong"), 2))
        painter.setBrush(theme_color("surface_raised"))
        painter.drawRoundedRect(QRectF(12, 33, width - 24, height - 62), 10, 10)
        painter.setPen(theme_color("text_muted"))
        painter.drawText(QRectF(12, 7, width - 24, 22), Qt.AlignmentFlag.AlignCenter, "SERVO")
        painter.translate(center_x, center_y)
        painter.rotate(angle)
        painter.setPen(QPen(accent.darker(135), 1.5))
        painter.setBrush(accent)
        painter.drawRoundedRect(QRectF(-6, -47, 12, 51), 5, 5)
        painter.rotate(-angle)
        painter.setPen(QPen(theme_color("border_strong"), 2))
        painter.setBrush(theme_color("surface"))
        painter.drawEllipse(QRectF(-11, -11, 22, 22))
        painter.setPen(theme_color("text"))
        painter.drawText(QRectF(-width / 2 + 8, height / 2 - 37, width - 16, 20), Qt.AlignmentFlag.AlignCenter,
                         f"{angle:.0f}°" if pulse is not None else "—")
        painter.restore()
