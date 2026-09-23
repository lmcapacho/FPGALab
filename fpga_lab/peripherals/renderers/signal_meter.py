"""Generic temporal-output meter for declarative external peripherals."""

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen

from ...theme import color as theme_color
from .base import NullInputMixin


class SignalMeterRenderer(NullInputMixin):
    """Show a terminal's measured high-time fraction, not LED visual persistence."""

    def __init__(self, visual: dict[str, object]):
        self._size = tuple(int(value) for value in visual["size"])
        self._terminal = str(visual["terminal"])
        self._color_property = str(visual.get("color_property", "color"))

    def size(self, peripheral) -> tuple[int, int]:
        return self._size  # type: ignore[return-value]

    def paint(self, painter: QPainter, rect, peripheral, state) -> None:
        del rect
        width, height = self._size
        body = QRectF(4, 4, width - 8, max(20, height - 30))
        observations = state.get("temporal", {})
        observation = observations.get(self._terminal) if isinstance(observations, dict) else None
        duty = max(0.0, min(float(observation.get("duty_cycle", 0.0)), 1.0)) if observation else 0.0
        accent = QColor(str(peripheral.properties.get(self._color_property, "#38bdf8")))
        painter.save()
        painter.setPen(QPen(theme_color("border_strong"), 1.5))
        painter.setBrush(theme_color("surface_raised"))
        painter.drawRoundedRect(body, 8, 8)
        painter.setPen(theme_color("text"))
        label = f"{duty * 100:.0f}%" if observation and state.get("powered") else "—"
        painter.drawText(QRectF(body.left() + 8, body.top() + 7, body.width() - 16, 23), Qt.AlignmentFlag.AlignCenter, label)
        track = QRectF(body.left() + 12, body.bottom() - 23, max(1, body.width() - 24), 9)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(theme_color("border"))
        painter.drawRoundedRect(track, 4, 4)
        if duty > 0 and observation and state.get("powered"):
            painter.setBrush(accent)
            painter.drawRoundedRect(QRectF(track.left(), track.top(), max(2, track.width() * duty), track.height()), 4, 4)
        painter.restore()
