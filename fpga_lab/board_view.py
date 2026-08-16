"""Vista escalable de una placa definida por SVG y JSON."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor, QPen
from PyQt6.QtSvgWidgets import QGraphicsSvgItem
from PyQt6.QtWidgets import QGraphicsRectItem, QGraphicsScene, QGraphicsView

from .board_layout import BoardLayout, BoardLayoutElement


class BoardLedItem(QGraphicsRectItem):
    def __init__(self, element: BoardLayoutElement):
        super().__init__(element.x, element.y, element.width, element.height)
        self._color = QColor(element.color)
        self.setPen(QPen(QColor("#475569"), 1.5))
        self.set_brightness(0.0)

    def set_brightness(self, brightness: float) -> None:
        value = max(0.0, min(1.0, brightness))
        color = QColor(self._color)
        color.setAlpha(round(255 * value))
        self.setBrush(QBrush(color))
        self.setPen(QPen(Qt.PenStyle.NoPen))


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
    """Renderiza el arte de la placa y superpone LEDs/botones interactivos."""

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
        artwork_bounds = self._add_svg()
        for element in layout.elements:
            element = self._map_element(element, artwork_bounds)
            if element.kind == "led":
                self._leds[element.signal] = BoardLedItem(element)
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

    def set_led_brightness(self, signal: str, brightness: float) -> None:
        if led := self._leds.get(signal):
            led.set_brightness(brightness)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
