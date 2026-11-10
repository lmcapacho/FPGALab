"""Read-only SPI monitor backed by synchronized edge-stream channels."""

from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QFont, QPainter, QPen

from ...i18n import t
from ..serial_runtime import SpiMonitorRuntime
from ...theme import color
from .base import NullInputMixin


class SpiMonitorRenderer(NullInputMixin):
    output_caption = "SPI"
    output_accessible_name = "SPI transfers"

    def __init__(self, visual: dict[str, object]):
        self._size = tuple(int(value) for value in visual["size"])
        self._mode_property = str(visual["mode_property"])
        self.runtime = SpiMonitorRuntime(visual)

    def size(self, peripheral) -> tuple[int, int]:
        return self._size  # type: ignore[return-value]

    def text_output_rect(self) -> tuple[int, int, int, int]:
        width, height = self._size
        return 10, 35, width - 20, height - 64

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

    @property
    def response_enabled(self) -> bool:
        return self.runtime.response_enabled

    @response_enabled.setter
    def response_enabled(self, enabled: bool) -> None:
        self.runtime.response_enabled = enabled

    def feed_edge_frame(self, peripheral, events, cycle, clock_hz, dropped) -> str:
        return self.runtime.feed_edge_frame(peripheral, events, cycle, clock_hz, dropped)

    def paint(self, painter: QPainter, rect, peripheral, state) -> None:
        del rect
        width, height = self._size
        snapshot = self.runtime.state
        painter.save()
        painter.setPen(QPen(color("border_strong"), 1.3))
        painter.setBrush(color("surface_raised"))
        painter.drawRoundedRect(QRectF(3, 3, width - 6, height - 31), 7, 7)
        painter.setPen(color("text_muted"))
        mode = peripheral.properties.get(self._mode_property, "0")
        painter.drawText(QRectF(11, 8, width - 22, 18), Qt.AlignmentFlag.AlignLeft, f"SPI · {t('Mode')} {mode}")
        if snapshot.dropped:
            painter.setPen(color("warning"))
            painter.drawText(QRectF(width - 105, 8, 94, 18), Qt.AlignmentFlag.AlignRight, f"DROP {snapshot.dropped}")
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
                "\n".join(snapshot.text.splitlines()[-7:]),
            )
        painter.restore()
