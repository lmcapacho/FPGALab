"""Temporal observation and physical models, independent from Qt."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SignalWindow:
    """Exact bit summary during a virtual-clock interval.

    ``high_halves / half_cycles`` is the observed duty cycle. It does not
    depend on the rate at which the interface is painted.
    """

    start: bool
    end: bool
    high_halves: int
    half_cycles: int
    edges: int

    @property
    def duty_cycle(self) -> float:
        return self.high_halves / self.half_cycles if self.half_cycles else float(self.end)


class PeripheralModel(Protocol):
    """Contract for any peripheral: virtual time in, visual state out."""

    def advance(self, signals: dict[str, SignalWindow], elapsed_seconds: float) -> object: ...


class LedModel:
    """LED with simple visual persistence; fast PWM is perceived as brightness."""

    def __init__(self, persistence_seconds: float = 0.015):
        self._persistence = persistence_seconds
        self._brightness = 0.0

    def advance(self, signals: dict[str, SignalWindow], elapsed_seconds: float) -> float:
        signal = signals["anode"]
        target = signal.duty_cycle
        alpha = min(1.0, elapsed_seconds / self._persistence) if self._persistence else 1.0
        self._brightness += (target - self._brightness) * alpha
        return self._brightness
