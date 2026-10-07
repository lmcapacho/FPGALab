"""Board definitions independent from HDL and the graphical interface."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .i18n import t

DEFAULT_BOARD_ID = "alhambra_ii"
DEFAULT_BOARD_PUBLIC_ID = "alhambra-ii"


@dataclass(frozen=True)
class BoardPin:
    id: str
    fpga_pin: str
    direction: str
    location: str
    active_low: bool = False


@dataclass(frozen=True)
class BoardDefinition:
    board_id: str
    label: str
    clock_hz: int
    pins: tuple[BoardPin, ...]
    led_endpoints: tuple[str, ...] = ()
    input_endpoints: tuple[str, ...] = ()
    clock_endpoint: str | None = None

    @classmethod
    def load(cls, path: str | Path) -> "BoardDefinition":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        pins = tuple(
            BoardPin(
                item["id"],
                str(item["fpga_pin"]),
                item.get("direction", "inout"),
                item.get("location", "header"),
                item.get("active_low", False),
            )
            for item in raw["pins"]
        )
        controls = raw.get("controls", {})
        board = cls(
            raw["id"], raw["label"], int(raw["clock_hz"]), pins,
            tuple(str(endpoint) for endpoint in controls.get("leds", ())),
            tuple(str(endpoint) for endpoint in controls.get("inputs", ())),
            str(controls["clock"]) if controls.get("clock") else None,
        )
        board.validate()
        return board

    def validate(self) -> None:
        ids = [pin.id for pin in self.pins]
        if len(ids) != len(set(ids)):
            raise ValueError(t("Board {board_id} has duplicate pin identifiers.", board_id=self.board_id))
        if self.clock_hz <= 0:
            raise ValueError(t("clock_hz must be positive."))
        known = {pin.id for pin in self.pins}
        for endpoint in (*self.led_endpoints, *self.input_endpoints):
            if endpoint not in known:
                raise ValueError(t("Board {board_id} references unknown control {endpoint!r}.", board_id=self.board_id, endpoint=endpoint))
        if any(not isinstance(pin.active_low, bool) for pin in self.pins):
            raise ValueError("Board pin active_low must be a boolean")
        if self.clock_endpoint is not None and self.clock_endpoint not in known:
            raise ValueError(t("Board {board_id} references unknown clock endpoint {endpoint!r}.", board_id=self.board_id, endpoint=self.clock_endpoint))

    def pin(self, endpoint: str) -> BoardPin:
        for pin in self.pins:
            if pin.id == endpoint:
                return pin
        raise KeyError(t("Board {board_id} does not have pin {endpoint!r}.", board_id=self.board_id, endpoint=endpoint))

    def endpoints_for_fpga_pin(self, fpga_pin: str) -> tuple[BoardPin, ...]:
        return tuple(pin for pin in self.pins if pin.fpga_pin == str(fpga_pin))

    def fpga_pin_for(self, endpoint: str) -> str:
        return self.pin(endpoint).fpga_pin

    def available_endpoints(self, direction: str | None = None) -> tuple[BoardPin, ...]:
        """Selectable endpoints; ``inout`` is available in both directions."""
        if direction is None:
            return self.pins
        return tuple(pin for pin in self.pins if pin.direction in {direction, "inout"})


def bundled_board_definition(board_id: str = DEFAULT_BOARD_ID) -> Path:
    """Return the packaged board definition used by the desktop application."""
    return Path(__file__).parent / "assets" / "boards" / board_id / "board.json"


def bundled_board_clock_hz(board_id: str = DEFAULT_BOARD_ID) -> int:
    """Return the default virtual clock declared by a bundled board."""
    return BoardDefinition.load(bundled_board_definition(board_id)).clock_hz
