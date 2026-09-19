"""Fallback renderer for catalog entries unavailable in this installation."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPen

from ...i18n import t
from ...theme import color
from .base import NullInputMixin


class UnsupportedRenderer(NullInputMixin):
    def size(self, peripheral) -> tuple[int, int]:
        return 190, 86

    def paint(self, painter, rect, peripheral, state) -> None:
        body = rect.adjusted(10, 30, -10, -10)
        pen = QPen(color("warning"), 1.5, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(body, 7, 7)
        painter.setPen(color("warning"))
        painter.drawText(
            body.adjusted(8, 3, -8, -3),
            Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
            t("Unsupported peripheral\n{kind}", kind=peripheral.kind),
        )
