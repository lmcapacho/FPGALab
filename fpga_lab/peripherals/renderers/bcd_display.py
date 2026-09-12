"""Integrated BCD-to-seven-segment display renderer."""

from __future__ import annotations

from PyQt6.QtGui import QColor, QPainter

from .base import NullInputMixin
from .seven_segment import paint_seven_segments
from ...wiring import PeripheralInstance


_DIGIT_SEGMENTS = (
    frozenset("abcdef"),
    frozenset("bc"),
    frozenset("abdeg"),
    frozenset("abcdg"),
    frozenset("bcfg"),
    frozenset("acdfg"),
    frozenset("acdefg"),
    frozenset("abc"),
    frozenset("abcdefg"),
    frozenset("abcdfg"),
    frozenset("abcefg"),
    frozenset("cdefg"),
    frozenset("adef"),
    frozenset("bcdeg"),
    frozenset("adefg"),
    frozenset("aefg"),
)


def bcd_segments(value: int) -> frozenset[str]:
    """Return illuminated segments for a four-bit decimal/hexadecimal code."""
    return _DIGIT_SEGMENTS[value] if 0 <= value < len(_DIGIT_SEGMENTS) else frozenset()


def active_bcd_segments(active: dict[str, bool], powered: bool) -> frozenset[str]:
    """Decode a complete sample only while the virtual circuit is powered."""
    terminals = ("A", "B", "C", "D")
    if not powered or not all(terminal in active for terminal in terminals):
        return frozenset()
    value = sum((1 << bit) for bit, terminal in enumerate(terminals) if active[terminal])
    return bcd_segments(value)


class BcdDisplayRenderer(NullInputMixin):
    def size(self, peripheral: PeripheralInstance) -> tuple[int, int]:
        return (150, 205)

    def paint(self, painter: QPainter, rect, peripheral: PeripheralInstance, state) -> None:
        active = state.get("active", {})
        enabled = active_bcd_segments(active, bool(state.get("powered", False)))
        brightness = {segment: 1.0 if segment in enabled else 0.0 for segment in "abcdefg"}
        paint_seven_segments(
            painter,
            brightness,
            QColor(str(peripheral.properties.get("color", "#ff3b30"))),
        )
