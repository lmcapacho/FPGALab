"""Stock workbench renderers keyed by ``visual.renderer`` in the manifest."""

from __future__ import annotations

from .button import ButtonRenderer
from .lamp import LampRenderer
from .sensor import SensorRenderer
from .seven_segment import SevenSegmentRenderer
from .traffic_light import TrafficLightRenderer
from .vga_monitor import VgaMonitorRenderer

_RENDERERS = {
    "lamp": LampRenderer,
    "traffic_light": TrafficLightRenderer,
    "seven_segment": SevenSegmentRenderer,
    "button": ButtonRenderer,
    "sensor": SensorRenderer,
    "vga_monitor": VgaMonitorRenderer,
}


def renderer_for(name: str):
    try:
        return _RENDERERS[name]()
    except KeyError as exc:
        raise ValueError(f"Unknown workbench renderer: {name}.") from exc
