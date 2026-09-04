"""Workbench renderer protocol and registry."""

from __future__ import annotations

from typing import Any, Protocol

from PyQt6.QtGui import QPainter

from ...wiring import PeripheralInstance


class WorkbenchRenderer(Protocol):
    def size(self, peripheral: PeripheralInstance) -> tuple[int, int]: ...
    def paint(self, painter: QPainter, rect, peripheral: PeripheralInstance, state: dict[str, Any]) -> None: ...
    def mouse_press(self, peripheral: PeripheralInstance, pos, input_changed) -> None: ...
    def mouse_release(self, peripheral: PeripheralInstance, pos, input_changed) -> None: ...


class NullInputMixin:
    def mouse_press(self, peripheral, pos, input_changed) -> None:
        return

    def mouse_release(self, peripheral, pos, input_changed) -> None:
        return


def lamp(painter: QPainter, x: int, y: int, brightness: float, color: str) -> None:
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QColor

    brightness = max(0.0, min(float(brightness), 1.0))
    off, on = QColor("#334155"), QColor(color)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(
        round(off.red() + (on.red() - off.red()) * brightness),
        round(off.green() + (on.green() - off.green()) * brightness),
        round(off.blue() + (on.blue() - off.blue()) * brightness),
    ))
    painter.drawEllipse(x - 10, y - 10, 20, 20)
