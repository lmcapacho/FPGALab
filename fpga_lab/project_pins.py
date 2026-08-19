"""Traducción entre redes HDL de un PCF y endpoints de una placa."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .board import BoardDefinition
from .constraints import PcfParser


@dataclass(frozen=True)
class ProjectPinBinding:
    hdl_net: str
    fpga_pin: str
    endpoint: str


@dataclass(frozen=True)
class ProjectPinMap:
    """Mapa derivado del PCF del diseño contra el pinout oficial de la placa."""

    bindings: tuple[ProjectPinBinding, ...]

    @classmethod
    def from_pcf(cls, board: BoardDefinition, pcf: str | Path) -> "ProjectPinMap":
        bindings: list[ProjectPinBinding] = []
        for constraint in PcfParser.parse_file(pcf):
            endpoints = board.endpoints_for_fpga_pin(constraint.fpga_pin)
            # SDA/SCL y DD4/DD5 comparten pin: se prefiere el endpoint del header.
            endpoint = next((pin for pin in endpoints if pin.location.startswith("header")), None)
            if endpoint is not None:
                bindings.append(ProjectPinBinding(constraint.net, constraint.fpga_pin, endpoint.id))
        return cls(tuple(bindings))

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
