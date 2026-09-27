"""Graphics item that presents and manipulates one catalog peripheral."""

from __future__ import annotations

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QBrush, QFont, QFontMetrics, QPainter, QPen, QTextCursor
from PyQt6.QtWidgets import (
    QApplication, QGraphicsItem, QGraphicsProxyWidget, QGraphicsRectItem,
    QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

from ..peripherals.catalog import spec_for
from ..peripherals.renderers import renderer_for
from ..peripherals.renderers.unsupported import UnsupportedRenderer
from ..peripherals.renderers.vga_monitor import VgaMonitorRenderer
from ..i18n import t
from ..theme import color, style_button


class WorkbenchPeripheralItem(QGraphicsRectItem):
    """Draggable item whose coordinates live in ``properties.position``."""

    def __init__(self, peripheral, configured, moved, input_changed, send_text=None):
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
        self._send_text = send_text
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
        self._text_input: QLineEdit | None = None
        self._send_button: QPushButton | None = None
        self._pending_text: str | None = None
        self._rx_output: QPlainTextEdit | None = None
        self._rx_caption: QLabel | None = None
        self._rx_copy_button: QPushButton | None = None
        self._rx_clear_button: QPushButton | None = None
        if hasattr(self._renderer, "text_output_rect"):
            region = self._renderer.text_output_rect()
            if region is not None:
                x, y, output_width, output_height = region
                container = QWidget()
                container.setObjectName("uartOutputContainer")
                column = QVBoxLayout(container)
                column.setContentsMargins(0, 0, 0, 0)
                column.setSpacing(3)
                actions = QHBoxLayout()
                actions.setContentsMargins(0, 0, 0, 0)
                actions.setSpacing(4)
                caption = QLabel("RX", container)
                caption.setObjectName("caption")
                self._rx_caption = caption
                actions.addWidget(caption)
                actions.addStretch()
                self._rx_copy_button = QPushButton(container)
                self._rx_copy_button.setFixedHeight(24)
                self._rx_copy_button.clicked.connect(self._copy_received_text)
                actions.addWidget(self._rx_copy_button)
                self._rx_clear_button = QPushButton(container)
                self._rx_clear_button.setFixedHeight(24)
                self._rx_clear_button.clicked.connect(self._clear_received_text)
                actions.addWidget(self._rx_clear_button)
                column.addLayout(actions)
                self._rx_output = QPlainTextEdit(container)
                self._rx_output.setReadOnly(True)
                self._rx_output.document().setMaximumBlockCount(4096)
                font = QFont("monospace")
                font.setStyleHint(QFont.StyleHint.TypeWriter)
                font.setPointSize(9)
                self._rx_output.setFont(font)
                column.addWidget(self._rx_output, 1)
                container.setProperty("scrollWheelContent", True)
                proxy = QGraphicsProxyWidget(self)
                proxy.setWidget(container)
                proxy.setPos(self._renderer_offset_x + x, y)
                proxy.resize(output_width, output_height)
                container.resize(output_width, output_height)
                self.retranslate_ui()
                self._update_rx_actions()
        if send_text is not None and hasattr(self._renderer, "text_input_rect"):
            region = self._renderer.text_input_rect()
            if region is not None:
                x, y, input_width, input_height = region
                container = QWidget()
                container.setObjectName("uartInputContainer")
                row = QHBoxLayout(container)
                row.setContentsMargins(0, 0, 0, 0)
                row.setSpacing(4)
                self._text_input = QLineEdit(container)
                self._text_input.setMaxLength(120)
                self._text_input.returnPressed.connect(self._submit_text)
                row.addWidget(self._text_input, 1)
                self._send_button = QPushButton(container)
                style_button(self._send_button, "secondary")
                self._send_button.clicked.connect(self._submit_text)
                row.addWidget(self._send_button)
                proxy = QGraphicsProxyWidget(self)
                proxy.setWidget(container)
                proxy.setPos(self._renderer_offset_x + x, y)
                proxy.resize(input_width, input_height)
                container.resize(input_width, input_height)
                container.setEnabled(False)
                self._text_container = container
                self.retranslate_ui()

    def retranslate_ui(self) -> None:
        if self._rx_caption is not None:
            self._rx_caption.setText(t(getattr(self._renderer, "output_caption", "RX")))
        if self._rx_output is not None:
            self._rx_output.setAccessibleName(t(getattr(self._renderer, "output_accessible_name", "Received UART text")))
        if self._rx_copy_button is not None:
            self._rx_copy_button.setText(t("Copy"))
            self._rx_copy_button.setToolTip(t("Copy received text"))
            self._rx_copy_button.setAccessibleName(t("Copy received text"))
        if self._rx_clear_button is not None:
            self._rx_clear_button.setText(t("Clear"))
            self._rx_clear_button.setToolTip(t("Clear received text"))
            self._rx_clear_button.setAccessibleName(t("Clear received text"))
        if self._text_input is not None:
            self._text_input.setPlaceholderText(t("Text to FPGA"))
            self._text_input.setAccessibleName(t("UART text to send"))
        if self._send_button is not None:
            self._send_button.setText(t("Send"))
            self._send_button.setAccessibleName(t("Send UART text"))

    def _submit_text(self) -> None:
        if not self._powered or self._text_input is None or self._send_text is None or self._pending_text is not None:
            return
        value = self._text_input.text()
        if not value:
            return
        terminal = getattr(self._renderer, "tx_channel", None)
        if terminal and self._send_text(self._peripheral.peripheral_id, terminal, value):
            self._pending_text = value
            self._send_button.setEnabled(False)

    def serial_send_result(self, text: str, accepted: bool) -> None:
        if self._pending_text != text:
            return
        self._pending_text = None
        if accepted and self._text_input is not None and self._text_input.text() == text:
            self._text_input.clear()
        if self._send_button is not None:
            self._send_button.setEnabled(self._powered)

    def _update_rx_actions(self) -> None:
        has_output = self._rx_output is not None and not self._rx_output.document().isEmpty()
        if self._rx_copy_button is not None:
            self._rx_copy_button.setEnabled(has_output)
        if self._rx_clear_button is not None:
            self._rx_clear_button.setEnabled(has_output)

    def _append_received_text(self, chunk: str) -> None:
        if not chunk or self._rx_output is None:
            return
        scrollbar = self._rx_output.verticalScrollBar()
        previous_position = scrollbar.value()
        follow_tail = previous_position >= scrollbar.maximum() - 1
        document = self._rx_output.document()
        cursor = QTextCursor(document)
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(chunk)
        excess = document.characterCount() - 1 - int(getattr(self._renderer, "output_limit", 65_536))
        if excess > 0:
            cursor.setPosition(0)
            cursor.setPosition(excess, QTextCursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()
        scrollbar.setValue(scrollbar.maximum() if follow_tail else min(previous_position, scrollbar.maximum()))
        self._update_rx_actions()

    def _copy_received_text(self) -> None:
        if self._rx_output is not None:
            QApplication.clipboard().setText(self._rx_output.toPlainText())

    def _clear_received_text(self) -> None:
        if self._rx_output is None:
            return
        self._rx_output.clear()
        if hasattr(self._renderer, "clear_output"):
            self._renderer.clear_output()
        self._update_rx_actions()
        self.update()

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

    def set_temporal_observation(
        self, terminal: str, duty_cycle: float, edge_rate_hz: float,
        pulse_high_seconds: float | None = None,
    ) -> None:
        """Publish a raw virtual-time signal window separately from visual LED persistence."""
        self._temporal_observations[terminal] = {
            "duty_cycle": max(0.0, min(float(duty_cycle), 1.0)),
            "edge_rate_hz": max(0.0, float(edge_rate_hz)),
            "pulse_high_seconds": pulse_high_seconds,
        }
        self.update()

    def set_snapshot(self, snapshot):
        self._snapshot = snapshot
        self.update()

    def feed_edge_events(self, terminal, events, cycle, clock_hz, dropped) -> None:
        """Forward generic timestamped transitions to a compatible renderer."""
        if hasattr(self._renderer, "feed_edges"):
            chunk = self._renderer.feed_edges(self._peripheral, terminal, events, cycle, clock_hz, dropped)
            if isinstance(chunk, str):
                self._append_received_text(chunk)
            self.update()

    @property
    def accepts_edge_frame(self) -> bool:
        return hasattr(self._renderer, "feed_edge_frame")

    def feed_edge_frame(self, events, cycle, clock_hz, dropped) -> None:
        """Forward one ordered multi-terminal frame to a protocol renderer."""
        if self.accepts_edge_frame:
            chunk = self._renderer.feed_edge_frame(self._peripheral, events, cycle, clock_hz, dropped)
            if isinstance(chunk, str):
                self._append_received_text(chunk)
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
        if self._text_input is not None:
            self._text_container.setEnabled(powered)
        if powered and hasattr(self._renderer, "sync_inputs"):
            self._renderer.sync_inputs(self._peripheral, self._input_changed)
        if not powered:
            self._pending_text = None
            if hasattr(self._renderer, "suspend_stream"):
                self._renderer.suspend_stream()
            elif hasattr(self._renderer, "reset_stream"):
                self._renderer.reset_stream()
            if hasattr(self._renderer, "cancel_interactions"):
                self._renderer.cancel_interactions()
            self._active.clear()
            self._brightness.clear()
            self._temporal_observations.clear()
            self._press_sources.clear()
            self._pressed = False
            self._snapshot = None
        if self._send_button is not None:
            self._send_button.setEnabled(powered and self._pending_text is None)
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
            "embedded_output": self._rx_output is not None,
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
