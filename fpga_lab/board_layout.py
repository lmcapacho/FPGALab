"""Declarative layout for an SVG board and its interactive controls."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .i18n import t
from .board import DEFAULT_BOARD_ID


@dataclass(frozen=True)
class BoardLayoutElement:
    id: str
    kind: str
    signal: str
    x: float
    y: float
    width: float
    height: float
    color: str = "#22c55e"
    role: str | None = None


@dataclass(frozen=True)
class BoardLayout:
    board_id: str
    source: Path
    svg: Path
    view_box: tuple[float, float, float, float]
    orientation: str
    rotation: int
    mirror_x: bool
    mirror_y: bool
    elements: tuple[BoardLayoutElement, ...]

    @classmethod
    def load(cls, path: str | Path) -> "BoardLayout":
        source = Path(path)
        raw = json.loads(source.read_text(encoding="utf-8"))
        elements = tuple(
            BoardLayoutElement(
                id=item["id"], kind=item["type"], signal=item["signal"],
                x=float(item["x"]), y=float(item["y"]),
                width=float(item["width"]), height=float(item["height"]),
                color=item.get("color", "#22c55e"),
                role=item.get("role"),
            )
            for item in raw["components"]
        )
        view_box = tuple(float(value) for value in raw["viewBox"])
        if len(view_box) != 4:
            raise ValueError(t("viewBox must have four values."))
        transform = raw.get("transform", {})
        rotation = int(transform.get("rotation", 90 if raw.get("orientation", "horizontal") == "vertical" else 0))
        layout = cls(
            raw["board_id"],
            source,
            source.parent / raw["svg"],
            view_box,
            raw.get("orientation", "horizontal"),
            rotation,
            bool(transform.get("mirror_x", False)),
            bool(transform.get("mirror_y", False)),
            elements,
        )
        layout.validate()
        return layout

    def validate(self) -> None:
        if not self.svg.is_file():
            raise FileNotFoundError(self.svg)
        if self.orientation not in {"horizontal", "vertical"}:
            raise ValueError(t("Board orientation must be horizontal or vertical."))
        if self.rotation not in {0, 90, 180, 270}:
            raise ValueError(t("Board rotation must be 0, 90, 180, or 270 degrees."))
        ids = [element.id for element in self.elements]
        if len(ids) != len(set(ids)):
            raise ValueError(t("Board layout contains duplicate identifiers."))
        for element in self.elements:
            if element.kind not in {"led", "button"}:
                raise ValueError(t("Unsupported component type: {kind}", kind=element.kind))
            if element.width <= 0 or element.height <= 0:
                raise ValueError(f"Invalid size for {element.id}")
            if element.role not in {None, "power", "reset"}:
                raise ValueError(f"Unsupported board control role: {element.role}")
            if element.role == "power" and element.kind != "led":
                raise ValueError("Power control must be an LED")
            if element.role == "reset" and element.kind != "button":
                raise ValueError("Reset control must be a button")
        roles = [element.role for element in self.elements if element.role is not None]
        if len(roles) != len(set(roles)):
            raise ValueError("Board layout contains duplicate control roles")

    def signal_for_role(self, role: str) -> str | None:
        return next((element.signal for element in self.elements if element.role == role), None)


def bundled_layout(board_id: str = DEFAULT_BOARD_ID) -> Path:
    return Path(__file__).parent / "assets" / "boards" / board_id / "layout.json"
