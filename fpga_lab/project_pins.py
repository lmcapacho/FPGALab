"""Translation between constrained HDL nets and board endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .board import BoardDefinition
from .constraints import parse_constraints_file


@dataclass(frozen=True)
class ProjectPinBinding:
    hdl_net: str
    fpga_pin: str
    endpoint: str


@dataclass(frozen=True)
class ProjectPinMap:
    """Map derived from design constraints and the official board pinout."""

    bindings: tuple[ProjectPinBinding, ...]

    @classmethod
    def from_constraints(cls, board: BoardDefinition, path: str | Path) -> "ProjectPinMap":
        bindings: list[ProjectPinBinding] = []
        for constraint in parse_constraints_file(path):
            endpoints = board.endpoints_for_fpga_pin(constraint.fpga_pin)
            # SDA/SCL and DD4/DD5 share pins: prefer the header endpoint.
            endpoint = next((pin for pin in endpoints if pin.location.startswith("header")), None)
            if endpoint is None and endpoints:
                endpoint = endpoints[0]
            if endpoint is not None:
                bindings.append(ProjectPinBinding(constraint.net, constraint.fpga_pin, endpoint.id))
        return cls(tuple(bindings))

    @classmethod
    def from_pcf(cls, board: BoardDefinition, pcf: str | Path) -> "ProjectPinMap":
        """Compatibility alias for existing callers."""
        return cls.from_constraints(board, pcf)

    def net_for(self, endpoint: str) -> str | None:
        for binding in self.bindings:
            if binding.endpoint == endpoint:
                return binding.hdl_net
        return None

    def endpoint_for(self, hdl_net: str) -> str | None:
        for binding in self.bindings:
            if binding.hdl_net == hdl_net:
                return binding.endpoint
        return None
