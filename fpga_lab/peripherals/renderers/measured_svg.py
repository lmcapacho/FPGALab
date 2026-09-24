"""Packaged SVG layers driven by one temporal measurement."""

from pathlib import Path

from PyQt6.QtCore import QRectF
from PyQt6.QtSvg import QSvgRenderer

from .base import NullInputMixin


class MeasuredSvgRenderer(NullInputMixin):
    def __init__(self, visual: dict[str, object], resource_root: Path | None):
        self._size = tuple(visual["size"])
        self._terminal = visual["terminal"]
        self._measurement = visual["measurement"]
        self._input_range = tuple(visual["input_range"])
        self._output_range = tuple(visual["output_range"])
        self._transform = visual["transform"]
        self._origin = tuple(visual["origin"])
        self._base = QSvgRenderer(str(resource_root / visual["base_svg"])) if resource_root else None
        self._moving = QSvgRenderer(str(resource_root / visual["moving_svg"])) if resource_root else None

    def size(self, peripheral) -> tuple[int, int]:
        return self._size

    def mapped_value(self, state: dict) -> float | None:
        if not state.get("powered"):
            return None
        temporal = state.get("temporal", {})
        observation = temporal.get(self._terminal) if isinstance(temporal, dict) else None
        raw = observation.get(self._measurement) if isinstance(observation, dict) else None
        if raw is None:
            return None
        low, high = self._input_range
        fraction = max(0.0, min(1.0, (float(raw) - low) / (high - low)))
        start, end = self._output_range
        return start + (end - start) * fraction

    def paint(self, painter, rect, peripheral, state) -> None:
        del rect, peripheral
        width, height = self._size
        target = QRectF(0, 0, width, max(1, height - 24))
        if self._base and self._base.isValid():
            self._base.render(painter, target)
        value = self.mapped_value(state)
        if not self._moving or not self._moving.isValid():
            return
        if value is None:
            value = (self._output_range[0] + self._output_range[1]) / 2 if self._transform == "rotate" else 0
        painter.save()
        x, y = self._origin
        painter.translate(x, y)
        if self._transform == "rotate":
            painter.rotate(value)
        else:
            painter.scale(value, 1)
        painter.translate(-x, -y)
        self._moving.render(painter, target)
        painter.restore()
