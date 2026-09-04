"""Laboratory project and virtual wiring resolution to HDL nets."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .board import BoardDefinition
from .constraints import PcfParser, PinConstraint
from .i18n import t
from .peripherals.catalog import load_catalog, spec_for

# Aliases computed from the bundled catalog (PR1 compatibility).
_CATALOG = load_catalog()
PERIPHERAL_TERMINALS = {
    spec.id: {terminal.name: terminal.direction for terminal in spec.terminals}
    for spec in _CATALOG.values()
}
PERIPHERAL_LABELS = {spec.id: spec.label for spec in _CATALOG.values()}
_DRIVING_TERMINALS = {spec.id: spec.driving_terminals() for spec in _CATALOG.values()}
_TERMINAL_DIRECTIONS = PERIPHERAL_TERMINALS
SUPPLY_ENDPOINTS = frozenset({"GND", "VCC"})


@dataclass(frozen=True)
class PeripheralInstance:
    peripheral_id: str
    kind: str
    connections: dict[str, str]
    properties: dict[str, object]


@dataclass(frozen=True)
class ResolvedWire:
    peripheral_id: str
    terminal: str
    board_endpoint: str
    hdl_net: str | None


@dataclass(frozen=True)
class VirtualLabProject:
    peripherals: tuple[PeripheralInstance, ...]

    @classmethod
    def load(cls, path: str | Path) -> "VirtualLabProject":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_raw(raw)

    @classmethod
    def from_raw(cls, raw: dict[str, object]) -> "VirtualLabProject":
        """Build a project from in-memory JSON before committing it to disk."""
        peripherals = tuple(
            PeripheralInstance(item["id"], item["type"], dict(item["connections"]), dict(item.get("properties", {})))
            for item in raw.get("peripherals", [])  # type: ignore[union-attr]
        )
        ids = [item.peripheral_id for item in peripherals]
        if len(ids) != len(set(ids)):
            raise ValueError(t("Multiple peripherals use the same id."))
        return cls(peripherals)

    def resolve(
        self, board: BoardDefinition, constraints: list[PinConstraint]
    ) -> tuple[ResolvedWire, ...]:
        by_pin = PcfParser.index_by_pin(constraints)
        input_drivers: set[str] = set()
        resolved: list[ResolvedWire] = []
        for peripheral in self.peripherals:
            spec = spec_for(peripheral.kind)
            known_terminals = spec.terminal_map()
            unknown = set(peripheral.connections) - set(known_terminals)
            if unknown:
                raise ValueError(t(
                    "{identifier}: invalid terminals: {terminals}.",
                    identifier=peripheral.peripheral_id,
                    terminals=", ".join(sorted(unknown)),
                ))
            for terminal, endpoint in peripheral.connections.items():
                terminal_spec = known_terminals[terminal]
                if endpoint in SUPPLY_ENDPOINTS:
                    if endpoint not in terminal_spec.supplies:
                        raise ValueError(t(
                            "{identifier}.{terminal}: {endpoint} is not supported by this terminal.",
                            identifier=peripheral.peripheral_id,
                            terminal=terminal,
                            endpoint=endpoint,
                        ))
                    resolved.append(ResolvedWire(peripheral.peripheral_id, terminal, endpoint, None))
                    continue
                board_pin = board.pin(endpoint)
                expected_direction = terminal_spec.direction
                if expected_direction and board_pin.direction not in {expected_direction, "inout"}:
                    raise ValueError(t(
                        "{identifier}.{terminal}: {endpoint} does not support {direction} direction.",
                        identifier=peripheral.peripheral_id,
                        terminal=terminal,
                        endpoint=endpoint,
                        direction=expected_direction,
                    ))
                constraint = by_pin.get(board_pin.fpga_pin)
                if terminal in spec.driving_terminals():
                    if endpoint in input_drivers:
                        raise ValueError(t(
                            "Input conflict: more than one peripheral drives {endpoint}.", endpoint=endpoint
                        ))
                    input_drivers.add(endpoint)
                resolved.append(
                    ResolvedWire(peripheral.peripheral_id, terminal, endpoint, constraint.net if constraint else None)
                )
        return tuple(resolved)
