"""Framework-free receive state and lifecycle for UART/SPI peripherals.

Hosts deliver virtual-cycle events on one owner thread. Qt renderers are adapters;
they do not own decoding rules. These runtimes do not execute native models,
schedule GUI timers or load executable code from peripheral packages.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..messages import t
from ..serial_edges import Transition, Uart8N1Decoder
from ..spi_edges import SpiDecoder, spi_response_byte

MAX_SERIAL_HISTORY = 65_536


@dataclass(frozen=True)
class SerialMonitorState:
    """Read-only snapshot suitable for a desktop or another presentation."""

    text: str
    dropped: int
    configured: bool
    framing_errors: int = 0
    invalid_baud: bool = False


class UartTerminalRuntime:
    """UART 8N1 receive history and partial-frame lifecycle, without widgets."""

    output_limit = MAX_SERIAL_HISTORY

    def __init__(self, visual: dict[str, object]):
        self._channel = str(visual["channel"])
        self._baud_property = str(visual["baud_property"])
        self.tx_channel = str(visual["tx_channel"]) if visual.get("tx_channel") else None
        self.reset_stream()

    @property
    def state(self) -> SerialMonitorState:
        return SerialMonitorState(
            self._text, self._dropped, self._decoder is not None,
            self._decoder.framing_errors if self._decoder is not None else 0,
            self._invalid_baud,
        )

    def reset_stream(self, *, preserve_output: bool = False) -> None:
        self._decoder: Uart8N1Decoder | None = None
        self._settings: tuple[int, int] | None = None
        self._last_cycle = 0
        if not preserve_output:
            self._text = ""
        self._dropped = 0
        self._invalid_baud = False

    def suspend_stream(self) -> None:
        """Discard a partial UART frame while retaining the readable history."""
        self.reset_stream(preserve_output=True)

    def clear_output(self) -> None:
        self._text = ""

    def feed_edges(self, peripheral, terminal, events, cycle, clock_hz, dropped) -> str:
        if terminal != self._channel or clock_hz <= 0:
            return ""
        if cycle < self._last_cycle:
            self.reset_stream(preserve_output=True)
        try:
            baud = int(peripheral.properties.get(self._baud_property, 115200))
        except (TypeError, ValueError):
            self.reset_stream(preserve_output=True)
            self._invalid_baud = True
            return ""
        settings = (clock_hz, baud)
        if settings != self._settings:
            self.reset_stream(preserve_output=True)
            try:
                self._decoder = Uart8N1Decoder(clock_hz, baud)
            except ValueError:
                self._invalid_baud = True
                return ""
            self._settings = settings
        if self._decoder is None:
            return ""
        received: list[str] = []
        if dropped:
            self._dropped += dropped
            self._decoder.reset()
            received.append("\n[" + t("Signal overflow") + "]\n")
            # A retained queue prefix may contain incomplete protocol frames.
            events = ()
        transitions = (Transition(event.cycle, event.level) for event in events)
        for value in self._decoder.feed(transitions, cycle):
            if value == 13:
                continue
            received.append(chr(value) if value == 10 or 32 <= value < 127 else f"\\x{value:02X}")
        self._last_cycle = cycle
        chunk = "".join(received)
        if chunk:
            self._text = (self._text + chunk)[-self.output_limit:]
        return chunk


class SpiMonitorRuntime:
    """Synchronized SPI receive history; MISO response execution stays native."""

    output_limit = MAX_SERIAL_HISTORY

    def __init__(self, visual: dict[str, object]):
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
        self._response_property = visual.get("response_property")
        self.response_enabled = False
        self.reset_stream()

    @property
    def state(self) -> SerialMonitorState:
        return SerialMonitorState(self._text, self._dropped, self._decoder is not None)

    def reset_stream(self, *, preserve_output: bool = False) -> None:
        self._decoder: SpiDecoder | None = None
        self._settings: tuple[int, str, str] | None = None
        self._last_cycle = 0
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
        if cycle < self._last_cycle:
            self.reset_stream(preserve_output=True)
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
            # A retained queue prefix cannot establish complete transactions.
            # Keep this contract even when frames bypass the standard worker.
            events = ()
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
            elif self.response_enabled and self._response_property:
                response = spi_response_byte(peripheral.properties.get(self._response_property, "A5"))
                line += f"  MISO TX {response:02X}"
            chunks.append(line + "\n")
        self._last_cycle = cycle
        chunk = "".join(chunks)
        if chunk:
            self._text = (self._text + chunk)[-self.output_limit:]
        return chunk
