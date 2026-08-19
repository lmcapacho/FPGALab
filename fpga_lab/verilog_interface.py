"""Lightweight discovery of the public interface of an exported Verilog module."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .profile import BoardProfile

_MODULE_START = re.compile(r"\bmodule\s+([A-Za-z_][A-Za-z0-9_$]*)")
_DECLARATION = re.compile(
    r"^(?:(input|output|inout)\s+)?(?:wire|reg|logic|signed|unsigned|tri|wand|wor)?\s*(\[[^]]+])?\s*([A-Za-z_][A-Za-z0-9_$]*)$"
)
_RANGE = re.compile(r"\[\s*(\d+)\s*:\s*(\d+)\s*]")


@dataclass(frozen=True)
class VerilogPort:
    """One public ANSI-style Verilog port."""

    name: str
    direction: str
    width: int


@dataclass(frozen=True)
class VerilogInterface:
    """Top-level module name and its publicly visible ports."""

    module_name: str
    ports: tuple[VerilogPort, ...]

    @classmethod
    def discover(cls, source: str | Path) -> "VerilogInterface":
        text = Path(source).read_text(encoding="utf-8")
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
        text = re.sub(r"//.*$", "", text, flags=re.MULTILINE)
        match = _MODULE_START.search(text)
        if match is None:
            raise ValueError("The exported Verilog file does not define a module.")
        module_name = match.group(1)
        opening = text.find("(", match.end())
        if opening < 0:
            raise ValueError(f"Module {module_name} has no ANSI-style port list.")
        if text[match.end():opening].strip().startswith("#"):
            parameter_opening = text.find("(", match.end())
            parameter_closing = _matching_parenthesis(text, parameter_opening)
            opening = text.find("(", parameter_closing + 1)
        closing = _matching_parenthesis(text, opening)
        ports = _parse_ports(text[opening + 1:closing])
        if not ports:
            raise ValueError(f"Module {module_name} has no supported public ports.")
        return cls(module_name, tuple(ports))

    def profile(self, board_name: str = "Alhambra II", clock_port: str | None = None) -> BoardProfile:
        """Create a generic ABI profile for every input and output port."""
        inputs = {port.name: port.width for port in self.ports if port.direction in {"input", "inout"}}
        outputs = {port.name: port.width for port in self.ports if port.direction == "output"}
        selected_clock = clock_port or _default_clock(inputs)
        if selected_clock not in inputs or inputs[selected_clock] != 1:
            raise ValueError(f"Clock port {selected_clock!r} is not a scalar input of {self.module_name}.")
        profile = BoardProfile(board_name, inputs, outputs, outputs, selected_clock)
        profile.validate()
        return profile


def _matching_parenthesis(text: str, opening: int) -> int:
    depth = 0
    for index in range(opening, len(text)):
        char = text[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
    raise ValueError("Unclosed Verilog port list.")


def _parse_ports(header: str) -> list[VerilogPort]:
    ports: list[VerilogPort] = []
    direction: str | None = None
    width = 1
    for raw_part in header.split(","):
        part = " ".join(raw_part.split())
        if not part:
            continue
        match = _DECLARATION.match(part)
        if match is None:
            raise ValueError(f"Unsupported Verilog port declaration: {part!r}")
        declared_direction, declared_range, name = match.groups()
        if declared_direction:
            direction = declared_direction
            width = _range_width(declared_range)
        elif declared_range:
            width = _range_width(declared_range)
        if direction is None:
            raise ValueError(f"Port {name!r} has no declared direction.")
        ports.append(VerilogPort(name, direction, width))
    return ports


def _range_width(range_text: str | None) -> int:
    if range_text is None:
        return 1
    match = _RANGE.fullmatch(range_text.replace(" ", ""))
    if match is None:
        raise ValueError(f"Only numeric Verilog port ranges are supported: {range_text!r}")
    return abs(int(match.group(1)) - int(match.group(2))) + 1


def _default_clock(inputs: dict[str, int]) -> str:
    for name in inputs:
        if name.lower() in {"clk", "clock"}:
            return name
    for name, width in inputs.items():
        if width == 1:
            return name
    raise ValueError("The module has no scalar input that can be used as its clock.")
