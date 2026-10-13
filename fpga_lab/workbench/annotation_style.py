"""Theme-aware appearance defaults for Lab annotations."""

import math

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPen

from ..theme import color


LINE_STYLES = {"solid": Qt.PenStyle.SolidLine, "dashed": Qt.PenStyle.DashLine, "dotted": Qt.PenStyle.DotLine}
STYLE_KEYS = ("stroke_color", "stroke_width", "stroke_style", "fill_enabled", "fill_color")


def annotation_color(data, field, fallback):
    value = data.get(field)
    candidate = QColor(value) if isinstance(value, str) else QColor()
    return candidate if candidate.isValid() else color(fallback)


def annotation_pen(data):
    try:
        width = float(data.get("stroke_width", 2))
        if not math.isfinite(width):
            width = 2
    except (ValueError, TypeError):
        width = 2
    style = data.get("stroke_style")
    pen = QPen(annotation_color(data, "stroke_color", "border_strong"), max(0.5, min(8, width)),
               LINE_STYLES.get(style, Qt.PenStyle.SolidLine) if isinstance(style, str) else Qt.PenStyle.SolidLine)
    if style == "dotted":
        # Qt's standard DotLine has rectangular, one-width-long marks.
        # Almost-zero dashes with round caps produce circular dots instead.
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setDashPattern([0.01, 2.5])
    return pen
