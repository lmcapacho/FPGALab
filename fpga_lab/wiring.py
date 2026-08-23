"""Laboratory project and virtual wiring resolution to HDL nets."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .board import BoardDefinition
from .constraints import PcfParser, PinConstraint

# GUI-independent catalog: each kind declares its HDL terminals.
PERIPHERAL_TERMINALS = {
    "led": {"anode": "output"},
    "traffic_light": {"red": "output", "yellow": "output", "green": "output"},
    "seven_segment": {"a": "output", "b": "output", "c": "output", "d": "output", "e": "output", "f": "output", "g": "output"},
    "button": {"signal": "input"},
    "sensor": {"signal": "input"},
}
PERIPHERAL_LABELS = {
    "led": "LED", "traffic_light": "Traffic light", "seven_segment": "Seven-segment display",
    "button": "Push button", "sensor": "Digital sensor",
}
_DRIVING_TERMINALS = {"button": {"signal"}, "sensor": {"signal"}}
_TERMINAL_DIRECTIONS = PERIPHERAL_TERMINALS


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
        peripherals = tuple(
            PeripheralInstance(item["id"], item["type"], dict(item["connections"]), dict(item.get("properties", {})))
            for item in raw.get("peripherals", [])
        )
        ids = [item.peripheral_id for item in peripherals]
        if len(ids) != len(set(ids)):
            raise ValueError("Multiple peripherals use the same id.")
        return cls(peripherals)

    def resolve(
        self, board: BoardDefinition, constraints: list[PinConstraint]
    ) -> tuple[ResolvedWire, ...]:
        by_pin = PcfParser.index_by_pin(constraints)
        input_drivers: set[str] = set()
        resolved: list[ResolvedWire] = []
        for peripheral in self.peripherals:
            known_terminals = _TERMINAL_DIRECTIONS.get(peripheral.kind)
            if known_terminals is None:
                raise ValueError(f"Unknown peripheral type: {peripheral.kind}.")
            unknown = set(peripheral.connections) - set(known_terminals)
            if unknown:
                raise ValueError(f"{peripheral.peripheral_id}: invalid terminals: {', '.join(sorted(unknown))}.")
            for terminal, endpoint in peripheral.connections.items():
                board_pin = board.pin(endpoint)
                expected_direction = _TERMINAL_DIRECTIONS.get(peripheral.kind, {}).get(terminal)
                if expected_direction and board_pin.direction not in {expected_direction, "inout"}:
                    raise ValueError(f"{peripheral.peripheral_id}.{terminal}: {endpoint} does not support {expected_direction} direction.")
                constraint = by_pin.get(board_pin.fpga_pin)
                if terminal in _DRIVING_TERMINALS.get(peripheral.kind, set()):
                    if endpoint in input_drivers:
                        raise ValueError(f"Input conflict: more than one peripheral drives {endpoint}.")
                    input_drivers.add(endpoint)
                resolved.append(
                    ResolvedWire(peripheral.peripheral_id, terminal, endpoint, constraint.net if constraint else None)
                )
        return tuple(resolved)
