"""Definiciones de placa independientes del HDL y de la interfaz gráfica."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BoardPin:
    id: str
    fpga_pin: str
    direction: str
    location: str


@dataclass(frozen=True)
class BoardDefinition:
    board_id: str
    label: str
    clock_hz: int
    pins: tuple[BoardPin, ...]

    @classmethod
    def load(cls, path: str | Path) -> "BoardDefinition":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        pins = tuple(
            BoardPin(
                item["id"],
                str(item["fpga_pin"]),
                item.get("direction", "inout"),
                item.get("location", "header"),
            )
            for item in raw["pins"]
        )
        board = cls(raw["id"], raw["label"], int(raw["clock_hz"]), pins)
        board.validate()
        return board

    def validate(self) -> None:
        ids = [pin.id for pin in self.pins]
        if len(ids) != len(set(ids)):
            raise ValueError(f"La placa {self.board_id} tiene identificadores de pin duplicados.")
        if self.clock_hz <= 0:
            raise ValueError("clock_hz debe ser positivo.")

    def pin(self, endpoint: str) -> BoardPin:
        for pin in self.pins:
            if pin.id == endpoint:
                return pin
        raise KeyError(f"La placa {self.board_id} no tiene el pin {endpoint!r}.")

    def endpoints_for_fpga_pin(self, fpga_pin: str) -> tuple[BoardPin, ...]:
        return tuple(pin for pin in self.pins if pin.fpga_pin == str(fpga_pin))

    def fpga_pin_for(self, endpoint: str) -> str:
        return self.pin(endpoint).fpga_pin
