"""Generic no-code peripheral renderer selected by terminal-state rules."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QRectF
from PyQt6.QtSvg import QSvgRenderer

from ...wiring import PeripheralInstance
from .base import NullInputMixin


class StateSvgRenderer(NullInputMixin):
    """Render one packaged SVG according to simple declarative signal rules."""

    def __init__(self, visual: dict[str, object], resource_root: Path | None):
        self._visual = dict(visual)
        self._size = tuple(int(value) for value in self._visual["size"])
        self._default = str(self._visual["default_state"])
        self._rules = tuple(self._visual.get("state_rules", ()))
        self._interactions = tuple(self._visual.get("interactions", ()))
        self._input_values = {
            str(dict(interaction)["terminal"]): False for interaction in self._interactions
        }
        self._renderers: dict[str, QSvgRenderer] = {}
        if resource_root is not None:
            for state, resource in dict(self._visual["states"]).items():
                self._renderers[str(state)] = QSvgRenderer(str(resource_root / str(resource)))

    def size(self, peripheral: PeripheralInstance) -> tuple[int, int]:
        return self._size  # type: ignore[return-value]

    def selected_state(self, state: dict[str, object]) -> str:
        values = state.get("active", {})
        if not isinstance(values, dict):
            values = {}
        values = {**values, **self._input_values}
        for raw_rule in self._rules:
            rule = dict(raw_rule)
            when = dict(rule["when"])
            if bool(values.get(str(when["terminal"]), False)) == bool(when["equals"]):
                return str(rule["state"])
        return self._default

    def paint(self, painter, rect, peripheral: PeripheralInstance, state) -> None:
        renderer = self._renderers.get(self.selected_state(state))
        if renderer is None or not renderer.isValid():
            return
        width, height = self._size
        renderer.render(painter, QRectF(0, 0, width, max(1, height - 24)))

    def mouse_press(self, peripheral, pos, input_changed) -> None:
        for raw_interaction in self._interactions:
            interaction = dict(raw_interaction)
            x, y, width, height = interaction["region"]
            if x <= pos.x() <= x + width and y <= pos.y() <= y + height:
                terminal = str(interaction["terminal"])
                self._input_values[terminal] = not self._input_values[terminal]
                input_changed(peripheral.peripheral_id, terminal, int(self._input_values[terminal]))
                return

    def sync_inputs(self, peripheral, input_changed) -> None:
        """Restore declarative input levels after the native simulation resets."""
        for terminal, value in self._input_values.items():
            input_changed(peripheral.peripheral_id, terminal, int(value))
