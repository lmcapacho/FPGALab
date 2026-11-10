"""Stock UART terminal for external edge-stream peripheral packages."""

from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QFont, QPainter, QPen

from ...i18n import t
from ..serial_runtime import UartTerminalRuntime
from ...theme import color
from .base import NullInputMixin


class UartTerminalRenderer(NullInputMixin):
    """Render bytes decoded from a manifest-selected edge channel."""

    def __init__(self, visual: dict[str, object]):
        self._size = tuple(int(value) for value in visual["size"])
        self._baud_property = str(visual["baud_property"])
        self.runtime = UartTerminalRuntime(visual)
        self.tx_channel = self.runtime.tx_channel

    def text_input_rect(self) -> tuple[int, int, int, int] | None:
        if self.tx_channel is None:
            return None
        width, height = self._size
        return 10, height - 65, width - 20, 30

    def text_output_rect(self) -> tuple[int, int, int, int]:
        width, height = self._size
        return 10, 35, width - 20, height - (107 if self.tx_channel else 64)

    def size(self, peripheral) -> tuple[int, int]:
        return self._size  # type: ignore[return-value]

    @property
    def output_limit(self) -> int:
        return self.runtime.output_limit

    @output_limit.setter
    def output_limit(self, value: int) -> None:
        self.runtime.output_limit = value

    def reset_stream(self, *, preserve_output: bool = False) -> None:
        self.runtime.reset_stream(preserve_output=preserve_output)

    def suspend_stream(self) -> None:
        self.runtime.suspend_stream()

    def clear_output(self) -> None:
        self.runtime.clear_output()

    def feed_edges(self, peripheral, terminal, events, cycle, clock_hz, dropped) -> str:
        return self.runtime.feed_edges(peripheral, terminal, events, cycle, clock_hz, dropped)

    def paint(self, painter: QPainter, rect, peripheral, state) -> None:
        del rect
        width, height = self._size
        body = QRectF(3, 3, width - 6, height - 31)
        painter.save()
        painter.setPen(QPen(color("border_strong"), 1.3))
        painter.setBrush(color("surface_raised"))
        painter.drawRoundedRect(body, 7, 7)
        painter.setPen(color("text_muted"))
        baud = peripheral.properties.get(self._baud_property, 115200)
        painter.drawText(QRectF(11, 8, width - 22, 18), Qt.AlignmentFlag.AlignLeft, f"UART · {baud} · 8N1")
        snapshot = self.runtime.state
        errors = snapshot.framing_errors
        if errors or snapshot.dropped or snapshot.invalid_baud:
            painter.setPen(color("warning"))
            painter.drawText(
                QRectF(width - 110, 8, 99, 18), Qt.AlignmentFlag.AlignRight,
                f"ERR {errors}" if errors else f"DROP {snapshot.dropped}" if snapshot.dropped else "ERR BAUD",
            )
        painter.setPen(QPen(color("border"), 1))
        painter.drawLine(9, 29, width - 9, 29)
        if not state.get("embedded_output"):
            painter.setPen(color("text"))
            font = QFont("monospace")
            font.setStyleHint(QFont.StyleHint.TypeWriter)
            font.setPointSize(9)
            painter.setFont(font)
            lines = snapshot.text.splitlines()[-6:]
            display = (
                t("Baud rate is too high for the virtual clock.") if snapshot.invalid_baud
                else "\n".join(line[-43:] for line in lines)
            )
            text_height = height - (105 if self.tx_channel else 67)
            painter.drawText(QRectF(11, 34, width - 22, text_height), Qt.AlignmentFlag.AlignTop, display)
        painter.restore()
