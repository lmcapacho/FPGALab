"""Board-constraint reading, starting with iCE40 PCF files."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_SET_IO = re.compile(r"^\s*set_io\s+(?P<body>.+?)\s*$")


@dataclass(frozen=True)
class PinConstraint:
    net: str
    fpga_pin: str
    options: tuple[str, ...] = ()
    source_line: int = 0


class PcfParser:
    """Parse `set_io` while retaining options for auditing."""

    @classmethod
    def parse_file(cls, path: str | Path) -> list[PinConstraint]:
        return cls.parse_text(Path(path).read_text(encoding="utf-8"))

    @staticmethod
    def parse_text(text: str) -> list[PinConstraint]:
        by_net: dict[str, PinConstraint] = {}
        for line_number, raw in enumerate(text.splitlines(), start=1):
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            if not line.startswith("set_io "):
                continue
            tokens = _SET_IO.match(line).group("body").split()
            options: list[str] = []
            while tokens and tokens[0].startswith("-"):
                options.append(tokens.pop(0))
            if len(tokens) != 2:
                raise ValueError(f"PCF línea {line_number}: set_io inválido.")
            net, fpga_pin = tokens
            constraint = PinConstraint(net, fpga_pin, tuple(options), line_number)
            previous = by_net.get(net)
            if previous and previous.fpga_pin != fpga_pin:
                raise ValueError(f"PCF: {net!r} tiene dos pines asignados.")
            by_net[net] = constraint
        return list(by_net.values())

    @staticmethod
    def index_by_pin(constraints: list[PinConstraint]) -> dict[str, PinConstraint]:
        result: dict[str, PinConstraint] = {}
        for constraint in constraints:
            previous = result.get(constraint.fpga_pin)
            if previous and previous.net != constraint.net:
                raise ValueError(f"PCF: pin {constraint.fpga_pin} tiene dos redes.")
            result[constraint.fpga_pin] = constraint
        return result
