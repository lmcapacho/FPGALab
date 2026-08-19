"""Scalable view of a board defined by SVG and JSON."""

from __future__ import annotations

import json
from collections.abc import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen
from PyQt6.QtSvgWidgets import QGraphicsSvgItem
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsRectItem, QGraphicsScene, QGraphicsView

from .board_layout import BoardLayout, BoardLayoutElement


class BoardLedItem(QGraphicsRectItem):
    def __init__(self, element: BoardLayoutElement):
        super().__init__(element.x, element.y, element.width, element.height)
        self._color = QColor(element.color)
        self._calibrating = False
        self._intensity = 0.0
        self.setPen(QPen(QColor("#475569"), 1.5))
        self.set_brightness(0.0)

    def set_brightness(self, brightness: float) -> None:
        self._intensity = max(0.0, min(1.0, brightness)) ** 0.38
        self.update()

    def paint(self, painter: QPainter, _option, _widget=None) -> None:
        if self._intensity:
            rect = self.rect()
            halo = QColor(self._color)
            halo.setAlpha(round(135 * self._intensity))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(halo)
            painter.drawRoundedRect(rect.adjusted(-1.4, -0.9, 1.4, 0.9), 1.6, 1.6)
            core = self._color.lighter(150)
            core.setAlpha(round(255 * self._intensity))
            painter.setBrush(core)
            painter.drawRoundedRect(rect.adjusted(0.25, 0.25, -0.25, -0.25), 0.7, 0.7)
        if self._calibrating:
            painter.setPen(QPen(QColor("#f43f5e"), 0.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.rect())


    def set_calibration(self, enabled: bool) -> None:
        self._calibrating = enabled
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, enabled)
        self.setPen(QPen(QColor("#f43f5e"), 0.5) if enabled else QPen(Qt.PenStyle.NoPen))


class BoardButtonItem(QGraphicsRectItem):
    def __init__(self, element: BoardLayoutElement, changed: Callable[[str, int], None]):
        super().__init__(element.x, element.y, element.width, element.height)
        self._signal = element.signal
        self._changed = changed
        self._idle = QBrush(QColor(0, 0, 0, 0))
        self._pressed = QBrush(QColor(255, 255, 255, 95))
        self.setBrush(self._idle)
        self.setPen(QPen(Qt.PenStyle.NoPen))
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event) -> None:
        self.setBrush(self._pressed)
        self._changed(self._signal, 1)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        self.setBrush(self._idle)
        self._changed(self._signal, 0)
        event.accept()


class BoardView(QGraphicsView):
    """Render board artwork and overlay interactive LEDs/buttons."""

    def __init__(self, layout: BoardLayout, input_changed: Callable[[str, int], None], parent=None):
        super().__init__(parent)
        self._layout = layout
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setBackgroundBrush(QColor("#0f172a"))
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._leds: dict[str, BoardLedItem] = {}
        self._led_items: dict[str, BoardLedItem] = {}
        self._calibration_mode = False
        artwork_bounds = self._add_svg()
        for element in layout.elements:
            element = self._map_element(element, artwork_bounds)
            if element.kind == "led":
                self._leds[element.signal] = BoardLedItem(element)
                self._led_items[element.id] = self._leds[element.signal]
                self._scene.addItem(self._leds[element.signal])
            elif element.kind == "button":
                self._scene.addItem(BoardButtonItem(element, input_changed))
        self._scene.setSceneRect(artwork_bounds)

    def _add_svg(self):
        artwork = QGraphicsSvgItem(str(self._layout.svg))
        artwork.setZValue(-10)
        self._scene.addItem(artwork)
        return artwork.boundingRect()

    def _map_element(self, element: BoardLayoutElement, artwork_bounds):
        origin_x, origin_y, layout_width, layout_height = self._layout.view_box
        return BoardLayoutElement(
            id=element.id, kind=element.kind, signal=element.signal, color=element.color,
            x=artwork_bounds.x() + (element.x - origin_x) * artwork_bounds.width() / layout_width,
            y=artwork_bounds.y() + (element.y - origin_y) * artwork_bounds.height() / layout_height,
            width=element.width * artwork_bounds.width() / layout_width,
            height=element.height * artwork_bounds.height() / layout_height,
        )

    def set_calibration_mode(self, enabled: bool) -> None:
        for item in self._led_items.values():
            item.set_calibration(enabled)

    def save_led_positions(self) -> None:
        raw = json.loads(self._layout.source.read_text(encoding="utf-8"))
        origin_x, origin_y, layout_width, layout_height = self._layout.view_box
        bounds = self._scene.sceneRect()
        by_id = {component["id"]: component for component in raw["components"]}
        for element_id, item in self._led_items.items():
            rect = item.sceneBoundingRect()
            component = by_id[element_id]
            component["x"] = round(origin_x + (rect.x() - bounds.x()) * layout_width / bounds.width(), 3)
            component["y"] = round(origin_y + (rect.y() - bounds.y()) * layout_height / bounds.height(), 3)
        self._layout.source.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")

    def set_led_brightness(self, signal: str, brightness: float) -> None:
        if led := self._leds.get(signal):
            led.set_brightness(brightness)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
