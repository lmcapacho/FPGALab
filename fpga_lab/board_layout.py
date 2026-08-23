"""Declarative layout for an SVG board and its interactive controls."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .i18n import t


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


@dataclass(frozen=True)
class BoardLayout:
    board_id: str
    source: Path
    svg: Path
    view_box: tuple[float, float, float, float]
    orientation: str
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
            )
            for item in raw["components"]
        )
        view_box = tuple(float(value) for value in raw["viewBox"])
        if len(view_box) != 4:
            raise ValueError(t("viewBox must have four values."))
        layout = cls(
            raw["board_id"],
            source,
            source.parent / raw["svg"],
            view_box,
            raw.get("orientation", "horizontal"),
            elements,
        )
        layout.validate()
        return layout

    def validate(self) -> None:
        if not self.svg.is_file():
            raise FileNotFoundError(self.svg)
        if self.orientation not in {"horizontal", "vertical"}:
            raise ValueError(t("Board orientation must be horizontal or vertical."))
        ids = [element.id for element in self.elements]
        if len(ids) != len(set(ids)):
            raise ValueError(t("Board layout contains duplicate identifiers."))
        for element in self.elements:
            if element.kind not in {"led", "button"}:
                raise ValueError(t("Unsupported component type: {kind}", kind=element.kind))
            if element.width <= 0 or element.height <= 0:
                raise ValueError(f"Invalid size for {element.id}")


def bundled_layout(board_id: str = "alhambra_ii") -> Path:
    return Path(__file__).parent / "assets" / "board_layouts" / f"{board_id}.json"
