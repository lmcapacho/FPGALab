"""Integrated BCD-to-seven-segment display renderer."""

from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter

from .base import NullInputMixin
from .seven_segment import paint_seven_segments
from ...theme import color as theme_color
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


def bcd_enable_active(active: dict[str, bool], endpoint: str | None) -> bool:
    """Treat an unconnected enable as active and a connected enable as active-high."""
    return endpoint is None or bool(active.get("enable", False))


def active_bcd_segments(
    active: dict[str, bool],
    powered: bool,
    *,
    enable_endpoint: str | None = None,
) -> frozenset[str]:
    """Decode a complete sample only while the virtual circuit is powered."""
    terminals = ("A", "B", "C", "D")
    if (
        not powered
        or not bcd_enable_active(active, enable_endpoint)
        or not all(terminal in active for terminal in terminals)
    ):
        return frozenset()
    value = sum((1 << bit) for bit, terminal in enumerate(terminals) if active[terminal])
    return bcd_segments(value)


class BcdDisplayRenderer(NullInputMixin):
    def size(self, peripheral: PeripheralInstance) -> tuple[int, int]:
        return (138, 150)

    def paint(self, painter: QPainter, rect, peripheral: PeripheralInstance, state) -> None:
        active = state.get("active", {})
        enabled = active_bcd_segments(
            active,
            bool(state.get("powered", False)),
            enable_endpoint=peripheral.connections.get("enable"),
        )
        brightness = {segment: 1.0 if segment in enabled else 0.0 for segment in "abcdefg"}
        painter.save()
        badge_font = QFont(painter.font())
        badge_font.setPointSizeF(7.0)
        badge_font.setBold(True)
        painter.setFont(badge_font)
        painter.setPen(theme_color("accent"))
        painter.drawText(QRectF(102, 18, 34, 16), Qt.AlignmentFlag.AlignCenter, "BCD")
        painter.translate(3, 0)
        painter.scale(0.88, 0.88)
        paint_seven_segments(
            painter,
            brightness,
            QColor(str(peripheral.properties.get("color", "#ff3b30"))),
            offset_y=-32,
        )
        painter.restore()
