"""Build native channel configuration using identifiers, never GUI objects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .catalog import load_catalog
from .manifest import PeripheralSpec
from ..profile import BoardProfile
from ..signals import signal_reference
from ..spi_edges import spi_response_byte
from ..wiring import SUPPLY_ENDPOINTS, ResolvedWire, VirtualLabProject

TerminalKey = tuple[str, str]
OutputCondition = tuple[int, int, bool]


@dataclass(frozen=True)
class ChannelPlan:
    """Ordered ABI channels and their corresponding Lab terminal identities.

    Positions in edge/drive/temporal tuples are native channel indices. Keep
    them unchanged when adapting the plan to an engine or presentation layer.
    Unavailable types and unmapped/invalid HDL references allocate no channels.
    """

    temporal_probes: tuple[tuple[OutputCondition, ...], ...] = ()
    temporal_bindings: tuple[TerminalKey, ...] = ()
    temporal_terminals: frozenset[TerminalKey] = frozenset()
    edge_bindings: tuple[tuple[str, str, int, int], ...] = ()
    drive_bindings: tuple[tuple[str, str, str, int, bool], ...] = ()
    spi_slaves: tuple[tuple, ...] = ()
    spi_response_peripherals: frozenset[str] = frozenset()
    warnings: tuple[str, ...] = ()

    @property
    def edge_channels(self) -> tuple[tuple[int, int], ...]:
        return tuple((output, bit) for _, _, output, bit in self.edge_bindings)

    @property
    def drive_channels(self) -> tuple[tuple[str, int, bool], ...]:
        return tuple((port, bit, idle) for _, _, port, bit, idle in self.drive_bindings)


def build_channel_plan(
    project: VirtualLabProject,
    wires: tuple[ResolvedWire, ...],
    profile: BoardProfile,
    *,
    catalog: Mapping[str, PeripheralSpec] | None = None,
) -> ChannelPlan:
    """Resolve manifest channels against already board/constraint-resolved wires.

    No files are changed and no model is configured. A host may supply its own
    catalog; otherwise the bundled/user declarative catalog is loaded.
    """
    catalog = load_catalog() if catalog is None else catalog
    nets = {(wire.peripheral_id, wire.terminal): wire.hdl_net for wire in wires}
    indexes = {name: index for index, name in enumerate(profile.outputs)}

    def condition(key: TerminalKey, expected: bool) -> OutputCondition | None:
        parsed = signal_reference(nets.get(key), profile.outputs)
        if parsed is None:
            return None
        name, bit = parsed
        return indexes[name], bit, expected

    probes = []
    temporal_bindings = []
    temporal_terminals = set()
    edges = []
    drives = []
    for peripheral in project.peripherals:
        spec = catalog.get(peripheral.kind)
        if spec is None:
            continue
        identifier = peripheral.peripheral_id
        temporal = spec.temporal
        if temporal is not None:
            if temporal["mode"] == "per_terminal":
                for terminal in spec.terminals:
                    key = (identifier, terminal.name)
                    predicate = condition(key, True)
                    if terminal.direction == "output" and predicate is not None:
                        probes.append((predicate,))
                        temporal_bindings.append(key)
            else:
                common = str(temporal["common_terminal"])
                polarity = str(peripheral.properties.get(str(temporal["polarity_property"]), "cathode"))
                supply = "GND" if polarity == "cathode" else "VCC"
                endpoint = peripheral.connections.get(common, supply)
                if endpoint in SUPPLY_ENDPOINTS:
                    common_conditions = [] if endpoint == supply else None
                else:
                    predicate = condition((identifier, common), polarity == "anode")
                    common_conditions = [predicate] if predicate is not None else None
                for terminal in temporal.get("active_terminals", ()):
                    key = (identifier, str(terminal))
                    temporal_terminals.add(key)
                    predicate = condition(key, polarity == "cathode")
                    if common_conditions is not None and predicate is not None:
                        probes.append(tuple([*common_conditions, predicate]))
                        temporal_bindings.append(key)
        for terminal in spec.edge_channels:
            predicate = condition((identifier, terminal), True)
            if predicate is not None:
                output, bit, _ = predicate
                edges.append((identifier, terminal, output, bit))
        for terminal in spec.drive_channels:
            parsed = signal_reference(nets.get((identifier, terminal)), profile.inputs)
            if parsed is not None and parsed[0] != profile.clock_name:
                port, bit = parsed
                drives.append((identifier, terminal, port, bit,
                               bool((spec.drive_idle or {}).get(terminal, False))))

    peripherals = {item.peripheral_id: item for item in project.peripherals}
    edge_sources = {(identifier, terminal): (output, bit)
                    for identifier, terminal, output, bit in edges}
    slaves = []
    enabled = set()
    warnings = []
    for channel, (identifier, terminal, _, _, _) in enumerate(drives):
        peripheral = peripherals[identifier]
        spec = catalog[peripheral.kind]
        visual = spec.visual
        if visual.get("miso_drive") != terminal:
            continue
        clock = edge_sources.get((identifier, visual["clock_channel"]))
        select = edge_sources.get((identifier, visual["select_channel"]))
        if clock is None or select is None:
            continue

        def value(field):
            name = visual[field]
            return peripheral.properties.get(name, spec.properties[name]["default"])

        try:
            slaves.append((*clock, *select, channel, int(value("mode_property")),
                           value("bit_order_property") == "lsb", value("cs_polarity_property") == "low",
                           spi_response_byte(value("response_property"))))
            enabled.add(identifier)
        except (ValueError, TypeError) as exc:
            warnings.append(str(exc))
    return ChannelPlan(
        tuple(probes), tuple(temporal_bindings),
        frozenset(temporal_terminals | set(temporal_bindings)),
        tuple(edges), tuple(drives), tuple(slaves), frozenset(enabled), tuple(warnings),
    )
