"""Read-only SPI monitor backed by synchronized edge-stream channels."""

from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QFont, QPainter, QPen

from ...i18n import t
from ...spi_edges import SpiDecoder
from ...theme import color
from .base import NullInputMixin


class SpiMonitorRenderer(NullInputMixin):
    output_limit = 65_536
    output_caption = "SPI"
    output_accessible_name = "SPI transfers"

    def __init__(self, visual: dict[str, object]):
        self._size = tuple(int(value) for value in visual["size"])
        self._channels = {
            str(visual["clock_channel"]): "sck",
            str(visual["select_channel"]): "cs",
            str(visual["mosi_channel"]): "mosi",
        }
        if visual.get("miso_channel"):
            self._channels[str(visual["miso_channel"])] = "miso"
        self._mode_property = str(visual["mode_property"])
        self._bit_order_property = str(visual["bit_order_property"])
        self._cs_polarity_property = str(visual["cs_polarity_property"])
        self.reset_stream()

    def size(self, peripheral) -> tuple[int, int]:
        return self._size  # type: ignore[return-value]

    def text_output_rect(self) -> tuple[int, int, int, int]:
        width, height = self._size
        return 10, 35, width - 20, height - 64

    def reset_stream(self, *, preserve_output: bool = False) -> None:
        self._decoder: SpiDecoder | None = None
        self._settings: tuple[int, str, str] | None = None
        if not preserve_output:
            self._text = ""
        self._dropped = 0
        self._shown_transaction: int | None = None

    def suspend_stream(self) -> None:
        self.reset_stream(preserve_output=True)

    def clear_output(self) -> None:
        self._text = ""

    def feed_edge_frame(self, peripheral, events, cycle, clock_hz, dropped) -> str:
        if clock_hz <= 0:
            return ""
        try:
            settings = (
                int(peripheral.properties.get(self._mode_property, 0)),
                str(peripheral.properties.get(self._bit_order_property, "msb")),
                str(peripheral.properties.get(self._cs_polarity_property, "low")),
            )
            if settings[2] not in ("low", "high"):
                return ""
            if settings != self._settings:
                self.reset_stream(preserve_output=True)
                self._decoder = SpiDecoder(settings[0], settings[1], settings[2] == "low")
                self._settings = settings
        except (TypeError, ValueError):
            return ""
        assert self._decoder is not None
        chunks: list[str] = []
        if dropped:
            self._dropped += dropped
            self._decoder.reset()
            self._shown_transaction = None
            chunks.append("\n[" + t("Signal overflow") + "]\n")
        transitions = (
            (event.cycle, self._channels[terminal], event.level)
            for terminal, event in events if terminal in self._channels
        )
        for byte in self._decoder.feed(transitions, cycle):
            prefix = f"#{byte.transaction} " if byte.transaction != self._shown_transaction else "   "
            self._shown_transaction = byte.transaction
            line = f"{prefix}MOSI {byte.mosi:02X}"
            if byte.miso is not None:
                line += f"  MISO {byte.miso:02X}"
            chunks.append(line + "\n")
        chunk = "".join(chunks)
        if chunk:
            self._text = (self._text + chunk)[-self.output_limit:]
        return chunk

    def paint(self, painter: QPainter, rect, peripheral, state) -> None:
        del rect
        width, height = self._size
        painter.save()
        painter.setPen(QPen(color("border_strong"), 1.3))
        painter.setBrush(color("surface_raised"))
        painter.drawRoundedRect(QRectF(3, 3, width - 6, height - 31), 7, 7)
        painter.setPen(color("text_muted"))
        mode = peripheral.properties.get(self._mode_property, "0")
        painter.drawText(QRectF(11, 8, width - 22, 18), Qt.AlignmentFlag.AlignLeft, f"SPI · {t('Mode')} {mode}")
        if self._dropped:
            painter.setPen(color("warning"))
            painter.drawText(QRectF(width - 105, 8, 94, 18), Qt.AlignmentFlag.AlignRight, f"DROP {self._dropped}")
        painter.setPen(QPen(color("border"), 1))
        painter.drawLine(9, 29, width - 9, 29)
        if not state.get("embedded_output"):
            painter.setPen(color("text"))
            font = QFont("monospace")
            font.setStyleHint(QFont.StyleHint.TypeWriter)
            font.setPointSize(9)
            painter.setFont(font)
            painter.drawText(
                QRectF(11, 34, width - 22, height - 68),
                Qt.AlignmentFlag.AlignTop,
                "\n".join(self._text.splitlines()[-7:]),
            )
        painter.restore()
