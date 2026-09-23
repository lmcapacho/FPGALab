"""Manifest schema for bundled workbench peripherals."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import math
import re
from typing import Any
from urllib.parse import urlparse


RESERVED_PROPERTIES = frozenset({"position"})

_VALID_DIRECTIONS = {"input", "output"}
_VALID_SIM_CLASSES = {"gpio_sampled", "gpio_temporal", "gpio_driven", "streaming_sink"}
_SUPPLY_ENDPOINTS = frozenset({"GND", "VCC"})
_VALID_PROP_TYPES = {"color", "color_map", "enum", "boolean", "string", "key_sequence"}
_PACKAGE_VERSION = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
_FPGALAB_VERSION = re.compile(r"^\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?$")
_LICENSE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+-]*$")


@dataclass(frozen=True)
class TerminalSpec:
    name: str
    direction: str
    width: int = 1
    required: bool = True
    supplies: tuple[str, ...] = ()


@dataclass(frozen=True)
class PackageMetadata:
    """Optional distribution identity for a shareable peripheral package."""

    version: str
    author_name: str
    author_url: str | None
    license: str
    repository: str | None
    minimum_fpgalab: str


@dataclass(frozen=True)
class PeripheralSpec:
    """One catalog entry loaded from ``manifest.json``."""

    id: str
    label: str
    category: str
    description: str
    keywords: tuple[str, ...]
    icon: str | None
    simulation_class: str
    terminals: tuple[TerminalSpec, ...]
    properties: dict[str, dict[str, Any]]
    visual: dict[str, Any]
    package: PackageMetadata | None = None
    sink_kind: str | None = None
    color_depth: int | None = None
    temporal: dict[str, Any] | None = None
    resource_root: Path | None = None

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


def parse_manifest(
    raw: dict[str, Any],
    *,
    source: str = "manifest.json",
    resource_root: Path | None = None,
) -> PeripheralSpec:
    """Validate and freeze one catalog JSON object."""
    api_version = raw.get("api_version", 1)
    if api_version != 1:
        raise ValueError(f"{source}: unsupported peripheral api_version {api_version!r}")
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
        supplies = tuple(str(value) for value in item.get("supplies", ()))
        if set(supplies) - _SUPPLY_ENDPOINTS:
            raise ValueError(f"{source}: {identifier}.{name} has unsupported supplies {supplies!r}")
        terminals.append(TerminalSpec(name, direction, width, bool(item.get("required", True)), supplies))
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
    if not (isinstance(size, list) and len(size) == 2 and all(isinstance(value, int) and value > 0 for value in size)):
        raise ValueError(f"{source}: {identifier} visual.size must be [width, height]")
    _validate_led_array_visual(visual, terminals, properties, source, identifier)
    _validate_state_svg_visual(visual, terminals, source, identifier, resource_root)
    _validate_signal_meter_visual(visual, terminals, properties, simulation, source, identifier)
    _validate_pulse_servo_visual(visual, terminals, properties, simulation, source, identifier)
    category = str(raw.get("category", "output")).strip().casefold()
    if not category:
        raise ValueError(f"{source}: {identifier} category must not be empty")
    description = str(raw.get("description", "")).strip()
    raw_keywords = raw.get("keywords", [])
    if not isinstance(raw_keywords, list) or not all(isinstance(value, str) for value in raw_keywords):
        raise ValueError(f"{source}: {identifier} keywords must be a list of strings")
    icon = raw.get("icon")
    if icon is not None:
        if not isinstance(icon, str) or not icon.strip():
            raise ValueError(f"{source}: {identifier} icon must be a relative file name")
        icon_path = PurePosixPath(icon)
        if icon_path.is_absolute() or ".." in icon_path.parts:
            raise ValueError(f"{source}: {identifier} icon must stay inside its peripheral directory")
    package = _optional_package_metadata(raw.get("package"), source, identifier)
    return PeripheralSpec(
        id=identifier,
        label=label,
        category=category,
        description=description,
        keywords=tuple(value.strip().casefold() for value in raw_keywords if value.strip()),
        icon=icon,
        simulation_class=sim_class,
        terminals=tuple(terminals),
        properties=properties,
        visual=visual,
        package=package,
        sink_kind=simulation.get("sink_kind"),
        color_depth=_optional_color_depth(simulation, source, identifier),
        temporal=_optional_temporal(simulation, source, identifier),
        resource_root=resource_root,
    )


def _optional_package_metadata(raw: Any, source: str, identifier: str) -> PackageMetadata | None:
    """Validate optional publication metadata without breaking legacy manifests."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError(f"{source}: {identifier} package metadata must be an object")
    version = raw.get("version")
    author = raw.get("author")
    license_id = raw.get("license")
    compatibility = raw.get("compatibility")
    if not isinstance(version, str) or _PACKAGE_VERSION.fullmatch(version) is None:
        raise ValueError(f"{source}: {identifier} package.version must use semantic versioning")
    if not isinstance(author, dict) or not isinstance(author.get("name"), str) or not author["name"].strip():
        raise ValueError(f"{source}: {identifier} package.author needs a name")
    author_url = author.get("url")
    if author_url is not None and not _valid_web_url(author_url):
        raise ValueError(f"{source}: {identifier} package.author.url must be an HTTP(S) URL")
    if not isinstance(license_id, str) or _LICENSE_ID.fullmatch(license_id) is None:
        raise ValueError(f"{source}: {identifier} package.license must be an SPDX-style identifier")
    repository = raw.get("repository")
    if repository is not None and not _valid_web_url(repository):
        raise ValueError(f"{source}: {identifier} package.repository must be an HTTP(S) URL")
    if not isinstance(compatibility, dict):
        raise ValueError(f"{source}: {identifier} package.compatibility must be an object")
    minimum = compatibility.get("minimum_fpgalab")
    if not isinstance(minimum, str) or _FPGALAB_VERSION.fullmatch(minimum) is None:
        raise ValueError(f"{source}: {identifier} minimum_fpgalab must be a FPGALab version")
    return PackageMetadata(
        version,
        author["name"].strip(),
        author_url,
        license_id,
        repository,
        minimum,
    )


def _valid_web_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _validate_led_array_visual(
    visual: dict[str, Any],
    terminals: list[TerminalSpec],
    properties: dict[str, dict[str, Any]],
    source: str,
    identifier: str,
) -> None:
    """Validate the reusable no-code LED-array renderer configuration."""
    if visual.get("renderer") != "led_array":
        return
    visual_terminals = visual.get("terminals")
    names = {terminal.name for terminal in terminals if terminal.direction == "output"}
    if (
        not isinstance(visual_terminals, list)
        or not visual_terminals
        or not all(isinstance(name, str) and name in names for name in visual_terminals)
        or len(visual_terminals) != len(set(visual_terminals))
    ):
        raise ValueError(f"{source}: {identifier} led_array terminals must be unique output terminals")
    if visual.get("orientation", "horizontal") not in {"horizontal", "vertical"}:
        raise ValueError(f"{source}: {identifier} led_array orientation must be horizontal or vertical")
    if visual.get("indicator_shape", "circle") not in {"circle", "rectangle"}:
        raise ValueError(f"{source}: {identifier} led_array indicator_shape must be circle or rectangle")
    if not isinstance(visual.get("show_labels", True), bool):
        raise ValueError(f"{source}: {identifier} led_array show_labels must be boolean")
    color_property = visual.get("color_property", "color")
    if properties.get(color_property, {}).get("type") != "color":
        raise ValueError(f"{source}: {identifier} led_array color_property must reference a color property")


def _validate_state_svg_visual(
    visual: dict[str, Any], terminals: list[TerminalSpec], source: str, identifier: str,
    resource_root: Path | None,
) -> None:
    """Validate a no-code renderer whose state selects one packaged SVG."""
    if visual.get("renderer") != "state_svg":
        return
    states = visual.get("states")
    if not isinstance(states, dict) or not states:
        raise ValueError(f"{source}: {identifier} state_svg needs a non-empty states object")
    for state, resource in states.items():
        if not isinstance(state, str) or not state or not isinstance(resource, str) or not resource:
            raise ValueError(f"{source}: {identifier} state_svg states must map names to SVG files")
        path = PurePosixPath(resource)
        if path.is_absolute() or ".." in path.parts or path.suffix.casefold() != ".svg":
            raise ValueError(f"{source}: {identifier} state_svg resources must be relative SVG files")
        if resource_root is not None and not (resource_root / resource).is_file():
            raise ValueError(f"{source}: {identifier} missing state SVG {resource!r}")
    default = visual.get("default_state")
    if not isinstance(default, str) or default not in states:
        raise ValueError(f"{source}: {identifier} state_svg default_state must name a declared state")
    rules = visual.get("state_rules", [])
    terminal_names = {terminal.name for terminal in terminals}
    if not isinstance(rules, list):
        raise ValueError(f"{source}: {identifier} state_svg state_rules must be a list")
    for rule in rules:
        when = rule.get("when") if isinstance(rule, dict) else None
        state_name = rule.get("state") if isinstance(rule, dict) else None
        terminal_name = when.get("terminal") if isinstance(when, dict) else None
        equals = when.get("equals") if isinstance(when, dict) else None
        if (
            not isinstance(rule, dict)
            or not isinstance(state_name, str)
            or state_name not in states
            or not isinstance(when, dict)
            or not isinstance(terminal_name, str)
            or terminal_name not in terminal_names
            or not isinstance(equals, (bool, int))
            or equals not in (0, 1)
        ):
            raise ValueError(f"{source}: {identifier} has an invalid state_svg rule")
    interactions = visual.get("interactions", [])
    input_names = {terminal.name for terminal in terminals if terminal.direction == "input"}
    width, height = visual["size"]
    visual_height = max(1, height - 24)
    if not isinstance(interactions, list):
        raise ValueError(f"{source}: {identifier} state_svg interactions must be a list")
    for interaction in interactions:
        region = interaction.get("region") if isinstance(interaction, dict) else None
        interaction_terminal = interaction.get("terminal") if isinstance(interaction, dict) else None
        valid_region = (
            isinstance(region, list)
            and len(region) == 4
            and all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in region)
            and region[0] >= 0
            and region[1] >= 0
            and region[2] > 0
            and region[3] > 0
            and region[0] + region[2] <= width
            and region[1] + region[3] <= visual_height
        )
        event = interaction.get("event") if isinstance(interaction, dict) else None
        action = interaction.get("action") if isinstance(interaction, dict) else None
        valid_behavior = (event, action) in {
            ("click", "toggle"),
            ("press_release", "momentary"),
        }
        if (
            not isinstance(interaction, dict)
            or not valid_behavior
            or not isinstance(interaction_terminal, str)
            or interaction_terminal not in input_names
            or not valid_region
        ):
            raise ValueError(f"{source}: {identifier} has an invalid state_svg interaction")


def _validate_signal_meter_visual(
    visual: dict[str, Any], terminals: list[TerminalSpec], properties: dict[str, dict[str, Any]],
    simulation: dict[str, Any], source: str, identifier: str,
) -> None:
    """Require a real temporal output for the generic high-time meter."""
    if visual.get("renderer") != "signal_meter":
        return
    output_names = {terminal.name for terminal in terminals if terminal.direction == "output" and terminal.width == 1}
    if visual.get("terminal") not in output_names:
        raise ValueError(f"{source}: {identifier} signal_meter.terminal must name a one-bit output")
    temporal = simulation.get("temporal")
    if simulation.get("class") != "gpio_temporal" or not isinstance(temporal, dict) or temporal.get("mode") != "per_terminal":
        raise ValueError(f"{source}: {identifier} signal_meter requires gpio_temporal per_terminal sampling")
    color_property = visual.get("color_property", "color")
    if properties.get(color_property, {}).get("type") != "color":
        raise ValueError(f"{source}: {identifier} signal_meter.color_property must reference a color property")


def _validate_pulse_servo_visual(
    visual: dict[str, Any], terminals: list[TerminalSpec], properties: dict[str, dict[str, Any]],
    simulation: dict[str, Any], source: str, identifier: str,
) -> None:
    if visual.get("renderer") != "pulse_servo":
        return
    output_names = {terminal.name for terminal in terminals if terminal.direction == "output" and terminal.width == 1}
    if visual.get("terminal") not in output_names:
        raise ValueError(f"{source}: {identifier} pulse_servo.terminal must name a one-bit output")
    temporal = simulation.get("temporal")
    if simulation.get("class") != "gpio_temporal" or not isinstance(temporal, dict) or temporal.get("mode") != "per_terminal":
        raise ValueError(f"{source}: {identifier} pulse_servo requires gpio_temporal per_terminal sampling")
    for name in ("pulse_min_us", "pulse_max_us", "angle_min_degrees", "angle_max_degrees"):
        value = visual.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{source}: {identifier} pulse_servo.{name} must be a finite number")
    if not 0 < visual["pulse_min_us"] < visual["pulse_max_us"] <= 1_000_000:
        raise ValueError(f"{source}: {identifier} pulse_servo pulse range is invalid")
    if not -360 <= visual["angle_min_degrees"] < visual["angle_max_degrees"] <= 360:
        raise ValueError(f"{source}: {identifier} pulse_servo angle range is invalid")
    color_property = visual.get("color_property", "color")
    if properties.get(color_property, {}).get("type") != "color":
        raise ValueError(f"{source}: {identifier} pulse_servo.color_property must reference a color property")


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


def _optional_temporal(simulation: dict[str, Any], source: str, identifier: str) -> dict[str, Any] | None:
    """Read an optional declarative predicate layout for temporal outputs."""
    temporal = simulation.get("temporal")
    if temporal is None:
        return None
    if simulation.get("class") != "gpio_temporal" or not isinstance(temporal, dict):
        raise ValueError(f"{source}: {identifier} temporal sampling requires simulation.class gpio_temporal")
    mode = temporal.get("mode")
    if mode not in {"per_terminal", "display_common"}:
        raise ValueError(f"{source}: {identifier} has invalid temporal mode {mode!r}")
    return dict(temporal)
