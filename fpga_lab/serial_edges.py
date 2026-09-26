"""Virtual-cycle edge decoding shared by serial workbench peripherals.

The native layer captures edges, not a protocol. Decoders consume the same
timestamped event stream, so a future SPI or I²C renderer can reuse the API.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Transition:
    cycle: int
    level: bool


class Uart8N1Decoder:
    """Decode an idle-high, LSB-first UART stream across UI-frame boundaries."""

    def __init__(self, clock_hz: int, baud: int):
        if clock_hz <= 0 or baud <= 0 or baud > clock_hz // 2:
            raise ValueError("UART baud must be positive and allow at least two cycles per bit.")
        self.cycles_per_bit = clock_hz / baud
        self.reset()

    def reset(self) -> None:
        self._level = True
        self._phase = "idle"
        self._next_sample = 0.0
        self._bit = 0
        self._value = 0
        self._last_cycle = 0
        self.framing_errors = 0

    def _sample_through(self, cycle: float, result: list[int]) -> None:
        while self._phase != "idle" and self._next_sample <= cycle:
            if self._phase == "start":
                if self._level:
                    self._phase = "idle"
                    continue
                self._phase = "data"
                self._next_sample += self.cycles_per_bit
            elif self._phase == "data":
                self._value |= int(self._level) << self._bit
                self._bit += 1
                self._next_sample += self.cycles_per_bit
                if self._bit == 8:
                    self._phase = "stop"
            else:
                if self._level:
                    result.append(self._value)
                else:
                    self.framing_errors += 1
                self._phase = "idle"

    def feed(self, transitions: Iterable[Transition], through_cycle: int) -> list[int]:
        """Process ordered transitions and sample completed bits up to a cycle."""
        result: list[int] = []
        for edge in transitions:
            if edge.cycle < self._last_cycle or edge.cycle > through_cycle:
                raise ValueError("UART transitions must be ordered within the current edge window.")
            self._sample_through(edge.cycle - 1e-9, result)
            previous = self._level
            self._level = edge.level
            self._last_cycle = edge.cycle
            if self._phase == "idle" and previous and not edge.level:
                self._phase = "start"
                self._next_sample = edge.cycle + self.cycles_per_bit / 2
                self._bit = self._value = 0
        if through_cycle < self._last_cycle:
            raise ValueError("UART edge window cannot move backwards.")
        self._sample_through(through_cycle, result)
        self._last_cycle = through_cycle
        return result


def uart_8n1_drive_events(data: bytes, start_cycle: int, clock_hz: int, baud: int) -> tuple[list[tuple[int, bool]], int]:
    """Return output-level changes at absolute virtual cycles for UART 8N1."""
    if start_cycle < 1 or clock_hz <= 0 or baud <= 0 or baud > clock_hz // 2:
        raise ValueError("UART transmission needs a clock and at least two cycles per bit.")
    events: list[tuple[int, bool]] = []
    level = True
    bit_index = 0
    for byte in data:
        for next_level in (False, *(bool(byte & (1 << bit)) for bit in range(8)), True):
            cycle = start_cycle + round(bit_index * clock_hz / baud)
            if next_level != level:
                events.append((cycle, next_level))
                level = next_level
            bit_index += 1
    end_cycle = start_cycle + round(bit_index * clock_hz / baud)
    return events, end_cycle
