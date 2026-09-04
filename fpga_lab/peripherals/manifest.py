"""Manifest schema for bundled workbench peripherals."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


RESERVED_PROPERTIES = frozenset({"position"})

_VALID_DIRECTIONS = {"input", "output"}
_VALID_SIM_CLASSES = {"gpio_sampled", "gpio_driven", "streaming_sink"}
_VALID_PROP_TYPES = {"color", "color_map", "enum", "boolean", "string"}


@dataclass(frozen=True)
class TerminalSpec:
    name: str
    direction: str
    width: int = 1
    required: bool = True


@dataclass(frozen=True)
class PeripheralSpec:
    """One catalog entry loaded from ``manifest.json``."""

    id: str
    label: str
    category: str
    simulation_class: str
    terminals: tuple[TerminalSpec, ...]
    properties: dict[str, dict[str, Any]]
    visual: dict[str, Any]
    sink_kind: str | None = None
    color_depth: int | None = None

    def terminal_map(self) -> dict[str, TerminalSpec]:
        return {terminal.name: terminal for terminal in self.terminals}

    def driving_terminals(self) -> frozenset[str]:
        if self.simulation_class != "gpio_driven":
            return frozenset()
        return frozenset(terminal.name for terminal in self.terminals)

    def required_terminals(self, properties: dict[str, Any] | None = None) -> tuple[str, ...]:
        """Completeness set: preset list replaces defaults when present."""
        props = properties or {}
        for name, schema in self.properties.items():
            presets = schema.get("presets")
            if schema.get("type") != "enum" or not isinstance(presets, dict):
                continue
            value = str(props.get(name, schema.get("default", "")))
            preset = presets.get(value)
            if isinstance(preset, dict) and "required_terminals" in preset:
                return tuple(str(item) for item in preset["required_terminals"])
        return tuple(terminal.name for terminal in self.terminals if terminal.required)


def parse_manifest(raw: dict[str, Any], *, source: str = "manifest.json") -> PeripheralSpec:
    """Validate and freeze one catalog JSON object."""
    identifier = raw.get("id")
    if not isinstance(identifier, str) or not identifier:
        raise ValueError(f"{source}: missing id")
    label = raw.get("label")
    if not isinstance(label, str) or not label:
        raise ValueError(f"{source}: {identifier} missing label")
    simulation = raw.get("simulation") or {}
    sim_class = simulation.get("class")
    if sim_class not in _VALID_SIM_CLASSES:
        raise ValueError(f"{source}: {identifier} has invalid simulation.class {sim_class!r}")
    terminals = []
    for item in raw.get("terminals") or []:
        name = item.get("name")
        direction = item.get("direction")
        if not name or direction not in _VALID_DIRECTIONS:
            raise ValueError(f"{source}: {identifier} has an invalid terminal {item!r}")
        width = int(item.get("width", 1))
        if width < 1:
            raise ValueError(f"{source}: {identifier}.{name} width must be positive")
        terminals.append(TerminalSpec(name, direction, width, bool(item.get("required", True))))
    names = [terminal.name for terminal in terminals]
    if len(names) != len(set(names)):
        raise ValueError(f"{source}: {identifier} has duplicate terminals")
    properties = dict(raw.get("properties") or {})
    reserved = set(properties) & RESERVED_PROPERTIES
    if reserved:
        raise ValueError(f"{source}: {identifier} must not declare reserved properties {sorted(reserved)}")
    for name, schema in properties.items():
        if not isinstance(schema, dict) or schema.get("type") not in _VALID_PROP_TYPES:
            raise ValueError(f"{source}: {identifier}.{name} has an invalid property schema")
    visual = dict(raw.get("visual") or {})
    if "renderer" not in visual or "size" not in visual:
        raise ValueError(f"{source}: {identifier} visual needs renderer and size")
    size = visual["size"]
    if not (isinstance(size, list) and len(size) == 2):
        raise ValueError(f"{source}: {identifier} visual.size must be [width, height]")
    return PeripheralSpec(
        id=identifier,
        label=label,
        category=str(raw.get("category", "output")),
        simulation_class=sim_class,
        terminals=tuple(terminals),
        properties=properties,
        visual=visual,
        sink_kind=simulation.get("sink_kind"),
        color_depth=_optional_color_depth(simulation, source, identifier),
    )


def _optional_color_depth(simulation: dict[str, Any], source: str, identifier: str) -> int | None:
    if "color_depth" not in simulation:
        return None
    try:
        depth = int(simulation["color_depth"])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{source}: {identifier} simulation.color_depth must be 1, 2, or 4") from exc
    if depth not in {1, 2, 4}:
        raise ValueError(f"{source}: {identifier} simulation.color_depth must be 1, 2, or 4")
    return depth
