"""Read physical pin assignments from PCF and a bounded XDC subset."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .i18n import t
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
                raise ValueError(f"PCF line {line_number}: invalid set_io.")
            net, fpga_pin = tokens
            constraint = PinConstraint(net, fpga_pin, tuple(options), line_number)
            previous = by_net.get(net)
            if previous and previous.fpga_pin != fpga_pin:
                raise ValueError(t("PCF: {net!r} has two assigned pins.", net=net))
            by_net[net] = constraint
        return list(by_net.values())

    @staticmethod
    def index_by_pin(constraints: list[PinConstraint]) -> dict[str, PinConstraint]:
        result: dict[str, PinConstraint] = {}
        for constraint in constraints:
            previous = result.get(constraint.fpga_pin)
            if previous and previous.net != constraint.net:
                raise ValueError(t("PCF: pin {pin} has two nets.", pin=constraint.fpga_pin))
            result[constraint.fpga_pin] = constraint
        return result


_XDC_PIN = re.compile(
    r"^set_property\s+PACKAGE_PIN\s+(\S+)\s+\[get_ports\s+(?:\{([^{}]+)\}|([^\]\s]+))\]$",
    re.IGNORECASE,
)
_XDC_DICT = re.compile(
    r"^set_property\s+-dict\s+\{([^{}]+)\}\s+\[get_ports\s+(?:\{([^{}]+)\}|([^\]\s]+))\]$",
    re.IGNORECASE,
)


class XdcParser:
    """Read literal PACKAGE_PIN assignments without evaluating Tcl commands."""

    @classmethod
    def parse_file(cls, path: str | Path) -> list[PinConstraint]:
        return cls.parse_text(Path(path).read_text(encoding="utf-8"))

    @staticmethod
    def parse_text(text: str) -> list[PinConstraint]:
        by_net: dict[str, PinConstraint] = {}
        logical_lines: list[tuple[int, str]] = []
        pending = ""
        start = 1
        for number, raw in enumerate(text.splitlines(), 1):
            line = raw.split("#", 1)[0].strip()
            if not pending:
                start = number
            pending += line.rstrip("\\").strip() + " "
            if line.endswith("\\"):
                continue
            logical_lines.append((start, pending.strip()))
            pending = ""
        if pending.strip():
            raise ValueError(f"XDC line {start}: unfinished continuation.")
        for number, line in logical_lines:
            if "PACKAGE_PIN" not in line.upper():
                continue
            match = _XDC_PIN.fullmatch(line)
            if match:
                pin, net = match.group(1), match.group(2) or match.group(3)
            else:
                match = _XDC_DICT.fullmatch(line)
                if not match:
                    raise ValueError(f"XDC line {number}: unsupported PACKAGE_PIN assignment.")
                properties = match.group(1).split()
                pins = [properties[i + 1] for i in range(0, len(properties) - 1, 2)
                        if properties[i].upper() == "PACKAGE_PIN"]
                if len(pins) != 1 or len(properties) % 2:
                    raise ValueError(f"XDC line {number}: invalid PACKAGE_PIN dictionary.")
                pin, net = pins[0], match.group(2) or match.group(3)
            if (not net or len(net.split()) != 1 or not pin
                    or any(character in net + pin for character in "$*?;\\")):
                raise ValueError(f"XDC line {number}: expected one literal port and pin.")
            previous = by_net.get(net)
            if previous and previous.fpga_pin != pin:
                raise ValueError(f"XDC line {number}: {net!r} has two assigned pins.")
            by_net[net] = PinConstraint(net, pin, source_line=number)
        constraints = list(by_net.values())
        PcfParser.index_by_pin(constraints)
        return constraints


def parse_constraints_file(path: str | Path) -> list[PinConstraint]:
    """Dispatch by extension; never treat an unknown format as an empty map."""
    source = Path(path)
    if source.suffix.lower() == ".pcf":
        return PcfParser.parse_file(source)
    if source.suffix.lower() == ".xdc":
        return XdcParser.parse_file(source)
    raise ValueError(f"Unsupported constraint format: {source.suffix}")
