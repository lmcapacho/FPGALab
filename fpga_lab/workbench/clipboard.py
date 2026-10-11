"""Bounded, versioned clipboard data for workbench selections."""

import json
import math

MIME_TYPE = "application/x-fpgalab-workbench+json"
MAX_BYTES = 1_000_000


def _position(value):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("Invalid clipboard position")
    if any(isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n) or abs(n) > 1_000_000 for n in value):
        raise ValueError("Invalid clipboard coordinate")


def decode_selection(data: bytes) -> dict:
    if len(data) > MAX_BYTES:
        raise ValueError("Clipboard selection is too large")
    raw = json.loads(data)
    if not isinstance(raw, dict) or raw.get("version") != 1:
        raise ValueError("Unsupported clipboard format")
    _position(raw.get("origin"))
    peripherals, annotations = raw.get("peripherals"), raw.get("annotations")
    if not isinstance(peripherals, list) or not isinstance(annotations, list) or not 0 < len(peripherals) + len(annotations) <= 512:
        raise ValueError("Invalid clipboard selection")
    for item in peripherals + annotations:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not isinstance(item.get("type"), str):
            raise ValueError("Invalid clipboard item")
    for item in peripherals:
        if not isinstance(item.get("properties"), dict):
            raise ValueError("Invalid clipboard properties")
        _position(item["properties"].get("position"))
    for item in annotations:
        if item["type"] not in {"text", "rectangle", "ellipse", "line"} or not isinstance(item.get("text", ""), str):
            raise ValueError("Invalid clipboard annotation")
        _position(item.get("position"))
        for field in ("width", "height"):
            number = item.get(field)
            if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number) or not 0 < number <= 100_000:
                raise ValueError("Invalid clipboard size")
    return raw
