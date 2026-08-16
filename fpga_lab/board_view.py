"""Vista escalable de una placa definida por SVG y JSON."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPen
from PyQt6.QtSvgWidgets import QGraphicsSvgItem
from PyQt6.QtWidgets import QGraphicsRectItem, QGraphicsScene, QGraphicsSimpleTextItem, QGraphicsView

from .board_layout import BoardLayout, BoardLayoutElement


class BoardLedItem(QGraphicsRectItem):
    def __init__(self, element: BoardLayoutElement):
        super().__init__(element.x, element.y, element.width, element.height)
        self._color = QColor(element.color)
        self.setPen(QPen(QColor("#475569"), 1.5))
        self.set_brightness(0.0)
        label = QGraphicsSimpleTextItem(element.id, self)
        label.setBrush(QBrush(QColor("#cbd5e1")))
        label.setPos(0, -15)
        label.setScale(0.65)

    def set_brightness(self, brightness: float) -> None:
        value = max(0.0, min(1.0, brightness))
        color = QColor(
            round(51 + (self._color.red() - 51) * value),
            round(65 + (self._color.green() - 65) * value),
            round(85 + (self._color.blue() - 85) * value),
        )
        self.setBrush(QBrush(color))
        self.setPen(QPen(self._color if value > 0.04 else QColor("#475569"), 1.5))


class BoardButtonItem(QGraphicsRectItem):
    def __init__(self, element: BoardLayoutElement, changed: Callable[[str, int], None]):
        super().__init__(element.x, element.y, element.width, element.height)
        self._signal = element.signal
        self._changed = changed
        self._idle = QBrush(QColor("#64748b"))
        self._pressed = QBrush(QColor("#94a3b8"))
        self.setBrush(self._idle)
        self.setPen(QPen(QColor("#e2e8f0"), 1.5))
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        label = QGraphicsSimpleTextItem(element.id, self)
        label.setBrush(QBrush(QColor("#0f172a")))
        label.setPos(7, 5)
        label.setScale(0.75)

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
        self._add_svg()
        for element in layout.elements:
            if element.kind == "led":
                self._leds[element.signal] = BoardLedItem(element)
                self._scene.addItem(self._leds[element.signal])
            elif element.kind == "button":
                self._scene.addItem(BoardButtonItem(element, input_changed))
        x, y, width, height = layout.view_box
        self._scene.setSceneRect(QRectF(x, y, width, height))

    def _add_svg(self) -> None:
        artwork = QGraphicsSvgItem(str(self._layout.svg))
        artwork.setZValue(-10)
        self._scene.addItem(artwork)

    def set_led_brightness(self, signal: str, brightness: float) -> None:
        if led := self._leds.get(signal):
            led.set_brightness(brightness)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
