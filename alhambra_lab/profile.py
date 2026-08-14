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

    @classmethod
    def load(cls, path: str | Path) -> "BoardProfile":
        source = Path(path)
        raw = json.loads(source.read_text(encoding="utf-8"))
        profile = cls(raw.get("board_name", "Alhambra II"), raw["inputs"], raw["outputs"])
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

    @property
    def ports(self) -> dict[str, int]:
        return self.inputs | self.outputs
