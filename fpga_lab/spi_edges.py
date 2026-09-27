"""Decode clocked SPI transfers from protocol-neutral edge events."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import groupby
from typing import Iterable


@dataclass(frozen=True)
class SpiByte:
    transaction: int
    mosi: int
    miso: int | None


class SpiDecoder:
    """Sample one byte per eight selected SCK edges while chip select is active."""

    def __init__(self, mode: int = 0, bit_order: str = "msb", cs_active_low: bool = True):
        if mode not in (0, 1, 2, 3) or bit_order not in ("msb", "lsb"):
            raise ValueError("SPI mode must be 0–3 and bit order must be msb or lsb.")
        self.mode = mode
        self.bit_order = bit_order
        self.cs_active_low = cs_active_low
        self.reset()

    def reset(self) -> None:
        self._levels: dict[str, bool] = {}
        self._last_cycle = 0
        self._bits_mosi: list[bool] = []
        self._bits_miso: list[bool] = []
        self.transactions = 0
        self.partial_bits = 0

    def _discard_partial(self) -> None:
        if self._bits_mosi:
            self.partial_bits += len(self._bits_mosi)
        self._bits_mosi.clear()
        self._bits_miso.clear()

    def _byte(self, bits: list[bool]) -> int:
        if self.bit_order == "lsb":
            return sum(int(level) << index for index, level in enumerate(bits))
        return sum(int(level) << (7 - index) for index, level in enumerate(bits))

    def feed(self, transitions: Iterable[tuple[int, str, bool]], through_cycle: int) -> list[SpiByte]:
        """Consume ordered (cycle, terminal, level) changes across UI frames.

        All changes observed in one virtual cycle are applied together before
        sampling SCK. Data changing in that same cycle therefore uses its new
        level; sources should establish the usual SPI setup time in their HDL.
        """
        ordered = list(transitions)
        if through_cycle < self._last_cycle:
            raise ValueError("SPI edge window cannot move backwards.")
        if any(
            cycle < self._last_cycle or cycle > through_cycle or terminal not in ("sck", "mosi", "miso", "cs")
            for cycle, terminal, _ in ordered
        ) or any(left[0] > right[0] for left, right in zip(ordered, ordered[1:])):
            raise ValueError("SPI transitions must be ordered within the current edge window.")
        received: list[SpiByte] = []
        for cycle, group in groupby(ordered, key=lambda edge: edge[0]):
            previous_clock = self._levels.get("sck")
            previous_selected = self._selected()
            for _, terminal, level in group:
                self._levels[terminal] = bool(level)
            selected = self._selected()
            if previous_selected and not selected:
                self._discard_partial()
            if selected and not previous_selected:
                self.transactions += 1
                self._discard_partial()
            current_clock = self._levels.get("sck")
            if not (selected and previous_selected) or previous_clock is None or current_clock == previous_clock:
                continue
            leading = previous_clock == bool(self.mode & 2)
            if leading != (self.mode % 2 == 0) or "mosi" not in self._levels:
                continue
            self._bits_mosi.append(self._levels["mosi"])
            if "miso" in self._levels:
                self._bits_miso.append(self._levels["miso"])
            if len(self._bits_mosi) == 8:
                received.append(SpiByte(
                    self.transactions,
                    self._byte(self._bits_mosi),
                    self._byte(self._bits_miso) if len(self._bits_miso) == 8 else None,
                ))
                self._bits_mosi.clear()
                self._bits_miso.clear()
        self._last_cycle = through_cycle
        return received

    def _selected(self) -> bool:
        cs = self._levels.get("cs")
        return cs is not None and cs == (not self.cs_active_low)
