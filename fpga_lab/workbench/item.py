"""Graphics item that presents and manipulates one catalog peripheral."""

from __future__ import annotations

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QBrush, QFont, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsRectItem

from ..peripherals.catalog import spec_for
from ..peripherals.renderers import renderer_for
from ..peripherals.renderers.unsupported import UnsupportedRenderer
from ..peripherals.renderers.vga_monitor import VgaMonitorRenderer
from ..theme import color


class WorkbenchPeripheralItem(QGraphicsRectItem):
    """Draggable item whose coordinates live in ``properties.position``."""

    def __init__(self, peripheral, configured, moved, input_changed):
        try:
            spec = spec_for(peripheral.kind)
        except ValueError:
            spec = None
        self._supported = spec is not None
        self._renderer = (
            renderer_for(spec.visual["renderer"], spec.visual, spec.resource_root)
            if spec is not None else UnsupportedRenderer()
        )
        self._compact_chrome = spec is not None and spec.visual.get("chrome") == "compact"
        renderer_width, height = self._renderer.size(peripheral)
        label_width = QFontMetrics(QFont()).horizontalAdvance(peripheral.peripheral_id) + 16
        width = max(renderer_width, label_width) if self._compact_chrome else renderer_width
        self._renderer_offset_x = (width - renderer_width) / 2
        super().__init__(0, 0, width, height)
        self._peripheral = peripheral
        self._configured = configured
        self._moved = moved
        self._input_changed = input_changed
        position = peripheral.properties.get("position", [16, 16])
        self.setPos(float(position[0]), float(position[1]))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self._active = {}
        self._brightness = {}
        self._temporal_observations = {}
        self._pressed = False
        self._press_sources: set[str] = set()
        self._sensor_value = False
        self._powered = False
        self._editable = True
        self._snapshot = None
        self._drag_dirty = False
        self._last_position = self.pos()

    @property
    def peripheral(self):
        """Expose the selected model instance to the workbench keyboard handler."""
        return self._peripheral

    @property
    def supported(self) -> bool:
        return self._supported

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self._editable:
            self._last_position = value
            self._drag_dirty = True
        return super().itemChange(change, value)

    def take_position_update(self) -> tuple[str, float, float] | None:
        """Return one pending position and mark it persisted by the view batch."""
        if not self._drag_dirty:
            return None
        self._drag_dirty = False
        return self._peripheral.peripheral_id, self._last_position.x(), self._last_position.y()

    def set_terminal(self, terminal, active):
        self.set_terminal_brightness(terminal, 1.0 if active else 0.0)

    def set_terminal_brightness(self, terminal: str, brightness: float) -> None:
        """Expose a continuous brightness value to catalog renderers."""
        brightness = max(0.0, min(float(brightness), 1.0))
        self._brightness[terminal] = brightness ** 0.38
        self._active[terminal] = brightness > 0.0
        self.update()

    def set_temporal_observation(self, terminal: str, duty_cycle: float, edge_rate_hz: float) -> None:
        """Publish a raw virtual-time signal window separately from visual LED persistence."""
        self._temporal_observations[terminal] = {
            "duty_cycle": max(0.0, min(float(duty_cycle), 1.0)),
            "edge_rate_hz": max(0.0, float(edge_rate_hz)),
        }
        self.update()

    def set_snapshot(self, snapshot):
        self._snapshot = snapshot
        self.update()

    def drop_vga_images(self):
        if isinstance(self._renderer, VgaMonitorRenderer):
            self._renderer.drop_images()
            self._snapshot = None
            self.update()

    def set_editable(self, enabled):
        self._editable = enabled
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, enabled)
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def set_powered(self, powered: bool) -> None:
        """Expose the virtual power state without inventing signal samples."""
        self._powered = powered
        if powered and hasattr(self._renderer, "sync_inputs"):
            self._renderer.sync_inputs(self._peripheral, self._input_changed)
        if not powered:
            if hasattr(self._renderer, "cancel_interactions"):
                self._renderer.cancel_interactions()
            self._active.clear()
            self._brightness.clear()
            self._temporal_observations.clear()
            self._press_sources.clear()
            self._pressed = False
            self._snapshot = None
        self.update()

    def set_button_pressed(self, source: str, pressed: bool) -> None:
        """Merge mouse and keyboard press states for a momentary button."""
        if self._peripheral.kind != "button":
            return
        previous = self._pressed
        if pressed:
            self._press_sources.add(source)
        else:
            self._press_sources.discard(source)
        self._pressed = bool(self._press_sources)
        if self._pressed != previous:
            self._input_changed(self._peripheral.peripheral_id, "signal", int(self._pressed))
            self.update()

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        button_active = self._peripheral.kind == "button" and self._pressed
        if self._compact_chrome:
            if self.isSelected():
                painter.setPen(QPen(color("accent"), 1.5))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 8, 8)
        else:
            border = color("success") if button_active else (
                color("border_strong") if not self.isSelected() else color("accent")
            )
            painter.setPen(QPen(border, 2))
            painter.setBrush(QBrush(color("success_surface") if button_active else color("surface_raised")))
            painter.drawRoundedRect(self.rect(), 10, 10)
        painter.setPen(color("text"))
        if self._compact_chrome:
            label_rect = self.rect().adjusted(4, self.rect().height() - 24, -4, -3)
            painter.drawText(
                label_rect,
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                self._peripheral.peripheral_id,
            )
        else:
            painter.drawText(
                self.rect().adjusted(10, 7, -8, -42),
                Qt.AlignmentFlag.AlignLeft,
                self._peripheral.peripheral_id,
            )
        painter.save()
        painter.translate(self._renderer_offset_x, 0)
        self._renderer.paint(painter, self.rect(), self._peripheral, {
            "active": self._active,
            "brightness": self._brightness,
            "temporal": self._temporal_observations,
            "pressed": self._pressed,
            "sensor_value": self._sensor_value,
            "powered": self._powered,
            "snapshot": self._snapshot,
        })
        painter.restore()

    def mousePressEvent(self, event):
        if self._editable and event.button() == Qt.MouseButton.LeftButton:
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        if self._peripheral.kind == "sensor":
            self._sensor_value = not self._sensor_value
            self._input_changed(self._peripheral.peripheral_id, "signal", int(self._sensor_value))
            self.update()
        elif self._peripheral.kind == "button":
            self.set_button_pressed("mouse", True)
        renderer_pos = event.pos() - QPointF(self._renderer_offset_x, 0)
        self._renderer.mouse_press(self._peripheral, renderer_pos, self._input_changed)
        self.update()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self._editable:
            self._configured(self._peripheral)
        event.accept()

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        if self._peripheral.kind == "button":
            self.set_button_pressed("mouse", False)
        renderer_pos = event.pos() - QPointF(self._renderer_offset_x, 0)
        self._renderer.mouse_release(self._peripheral, renderer_pos, self._input_changed)
