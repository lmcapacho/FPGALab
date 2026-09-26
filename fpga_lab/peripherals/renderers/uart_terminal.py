"""Stock UART terminal for external edge-stream peripheral packages."""

from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QFont, QPainter, QPen

from ...i18n import t
from ...serial_edges import Transition, Uart8N1Decoder
from ...theme import color
from .base import NullInputMixin


class UartTerminalRenderer(NullInputMixin):
    """Render bytes decoded from a manifest-selected edge channel."""

    def __init__(self, visual: dict[str, object]):
        self._size = tuple(int(value) for value in visual["size"])
        self._channel = str(visual["channel"])
        self._baud_property = str(visual["baud_property"])
        self.tx_channel = str(visual["tx_channel"]) if visual.get("tx_channel") else None
        self.reset_stream()

    def text_input_rect(self) -> tuple[int, int, int, int] | None:
        if self.tx_channel is None:
            return None
        width, height = self._size
        return 10, height - 65, width - 20, 30

    def size(self, peripheral) -> tuple[int, int]:
        return self._size  # type: ignore[return-value]

    def reset_stream(self) -> None:
        self._decoder: Uart8N1Decoder | None = None
        self._settings: tuple[int, int] | None = None
        self._text = ""
        self._dropped = 0
        self._invalid_baud = False

    def feed_edges(self, peripheral, terminal, events, cycle, clock_hz, dropped) -> None:
        if terminal != self._channel or clock_hz <= 0:
            return
        try:
            baud = int(peripheral.properties.get(self._baud_property, 115200))
        except (TypeError, ValueError):
            self.reset_stream()
            self._invalid_baud = True
            return
        settings = (clock_hz, baud)
        if settings != self._settings:
            self.reset_stream()
            try:
                self._decoder = Uart8N1Decoder(clock_hz, baud)
            except ValueError:
                self._invalid_baud = True
                return
            self._settings = settings
        if self._decoder is None:
            return
        if dropped:
            self._dropped += dropped
            self._decoder.reset()
            self._text = (self._text + "\n[" + t("Signal overflow") + "]\n")[-2048:]
        transitions = (Transition(event.cycle, event.level) for event in events)
        for value in self._decoder.feed(transitions, cycle):
            if value == 13:
                continue
            self._text += chr(value) if value == 10 or 32 <= value < 127 else f"\\x{value:02X}"
        self._text = self._text[-2048:]

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
        errors = self._decoder.framing_errors if self._decoder is not None else 0
        if errors or self._dropped:
            painter.setPen(color("warning"))
            painter.drawText(
                QRectF(width - 110, 8, 99, 18), Qt.AlignmentFlag.AlignRight,
                f"ERR {errors}" if errors else f"DROP {self._dropped}",
            )
        painter.setPen(QPen(color("border"), 1))
        painter.drawLine(9, 29, width - 9, 29)
        painter.setPen(color("text"))
        font = QFont("monospace")
        font.setStyleHint(QFont.StyleHint.TypeWriter)
        font.setPointSize(9)
        painter.setFont(font)
        lines = self._text.splitlines()[-6:]
        display = (
            t("Baud rate is too high for the virtual clock.") if self._invalid_baud
            else "\n".join(line[-43:] for line in lines) if state.get("powered") else ""
        )
        text_height = height - (105 if self.tx_channel else 67)
        painter.drawText(QRectF(11, 34, width - 22, text_height), Qt.AlignmentFlag.AlignTop, display)
        painter.restore()
