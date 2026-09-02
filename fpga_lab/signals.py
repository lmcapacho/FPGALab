"""Parse PCF net names such as ``vinit[2]`` into ABI port + bit."""

from __future__ import annotations

import re

_SIGNAL_REFERENCE = re.compile(r"([A-Za-z_][A-Za-z0-9_$]*)(?:\[(\d+)])?$")


def signal_reference(net: str | None, ports: dict[str, int]) -> tuple[str, int] | None:
    """Convert a PCF net such as ``vinit[2]`` into an ABI port and bit."""
    match = _SIGNAL_REFERENCE.fullmatch(net or "")
    if match is None:
        return None
    name, raw_bit = match.groups()
    bit = int(raw_bit) if raw_bit else 0
    if name not in ports or bit >= ports[name]:
        return None
    return name, bit
