"""Perfil explícito de los puertos Verilog visibles en la ABI del simulador."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")


@dataclass(frozen=True)
class BoardProfile:
    board_name: str
    inputs: dict[str, int]
    outputs: dict[str, int]
    observed: dict[str, int] | None = None

    @classmethod
    def load(cls, path: str | Path) -> "BoardProfile":
        source = Path(path)
        raw = json.loads(source.read_text(encoding="utf-8"))
        profile = cls(raw.get("board_name", "Alhambra II"), raw["inputs"], raw["outputs"], raw.get("observed"))
        profile.validate()
        return profile

    def validate(self) -> None:
        if self.inputs.get("clk") != 1:
            raise ValueError("El perfil debe declarar una entrada escalar 'clk'.")
        for direction, ports in (("inputs", self.inputs), ("outputs", self.outputs)):
            for name, width in ports.items():
                if not _IDENTIFIER.fullmatch(name):
                    raise ValueError(f"Nombre de puerto inválido en {direction}: {name!r}")
                if not isinstance(width, int) or not 1 <= width <= 64:
                    raise ValueError(f"Ancho inválido para {name}: {width!r}; use 1..64.")

        if self.observed is not None:
            for name, width in self.observed.items():
                if self.outputs.get(name) != width:
                    raise ValueError("Cada señal observada debe coincidir con una salida declarada.")

    @property
    def ports(self) -> dict[str, int]:
        return self.inputs | self.outputs

    @property
    def observed_bits(self) -> tuple[tuple[str, int], ...]:
        """Bits de salida en el orden estable usado por la sonda temporal."""
        return tuple(
            (name, bit)
            for name, width in (self.observed if self.observed is not None else self.outputs).items()
            for bit in range(width)
        )
