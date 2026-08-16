"""Observación temporal y modelos físicos, independientes de Qt."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SignalWindow:
    """Resumen exacto de un bit durante un intervalo de reloj virtual.

    ``high_halves / half_cycles`` equivale al ciclo de trabajo observado. No
    depende de la frecuencia a la que se pinte la interfaz.
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
    """Contrato de cualquier periférico: tiempo virtual entra, estado visual sale."""

    def advance(self, signals: dict[str, SignalWindow], elapsed_seconds: float) -> object: ...


class LedModel:
    """LED con persistencia visual simple; PWM rápido se percibe como brillo."""

    def __init__(self, persistence_seconds: float = 0.015):
        self._persistence = persistence_seconds
        self._brightness = 0.0

    def advance(self, signals: dict[str, SignalWindow], elapsed_seconds: float) -> float:
        signal = signals["anode"]
        target = signal.duty_cycle
        alpha = min(1.0, elapsed_seconds / self._persistence) if self._persistence else 1.0
        self._brightness += (target - self._brightness) * alpha
        return self._brightness
