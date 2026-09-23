"""Stock workbench renderers keyed by ``visual.renderer`` in the manifest."""

from __future__ import annotations

from .button import ButtonRenderer
from .bcd_display import BcdDisplayRenderer
from .dip_switch import DipSwitchRenderer
from .lamp import LampRenderer
from .led_array import LedArrayRenderer
from .sensor import SensorRenderer
from .state_svg import StateSvgRenderer
from .signal_meter import SignalMeterRenderer
from .seven_segment import SevenSegmentRenderer
from .traffic_light import TrafficLightRenderer
from .toggle_switch import ToggleSwitchRenderer
from .vga_monitor import VgaMonitorRenderer

_RENDERERS = {
    "bcd_display": BcdDisplayRenderer,
    "dip_switch": DipSwitchRenderer,
    "lamp": LampRenderer,
    "traffic_light": TrafficLightRenderer,
    "toggle_switch": ToggleSwitchRenderer,
    "seven_segment": SevenSegmentRenderer,
    "button": ButtonRenderer,
    "sensor": SensorRenderer,
    "vga_monitor": VgaMonitorRenderer,
}


def renderer_for(name: str, visual: dict[str, object] | None = None, resource_root=None):
    if name == "led_array":
        return LedArrayRenderer(visual or {})
    if name == "state_svg":
        return StateSvgRenderer(visual or {}, resource_root)
    if name == "signal_meter":
        return SignalMeterRenderer(visual or {})
    try:
        return _RENDERERS[name]()
    except KeyError as exc:
        raise ValueError(f"Unknown workbench renderer: {name}.") from exc
