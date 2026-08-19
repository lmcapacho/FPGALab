"""Minimal position editor for SVG board layouts."""

from __future__ import annotations

import json

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtSvgWidgets import QGraphicsSvgItem
from PyQt6.QtWidgets import (
    QColorDialog, QDialog, QDialogButtonBox, QFormLayout, QFrame, QInputDialog, QGraphicsItem, QGraphicsRectItem,
    QGraphicsScene, QGraphicsView, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
)

from .board_layout import BoardLayout, BoardLayoutElement


class EditableItem(QGraphicsRectItem):
    def __init__(self, element: BoardLayoutElement):
        super().__init__(element.x, element.y, element.width, element.height)
        self.element_id = element.id
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def paint(self, painter: QPainter, _option, _widget=None) -> None:
        painter.setPen(QPen(QColor("#f43f5e") if self.isSelected() else QColor("#facc15"), 0.65))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self.rect())


class EditorCanvas(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.key_handler = None
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def keyPressEvent(self, event) -> None:
        if self.key_handler and self.key_handler(event):
            event.accept()
            return
        super().keyPressEvent(event)

    def wheelEvent(self, event) -> None:
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)


class BoardLayoutEditor(QDialog):
    """Place components over the SVG and persist their coordinates."""

    def __init__(self, layout: BoardLayout, parent=None):
        super().__init__(parent)
        self._layout = layout
        self.setWindowTitle(f"Editar layout · {layout.board_id}")
        self.setWindowFlag(Qt.WindowType.Window, True)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)
        self.setMinimumSize(900, 600)
        self.resize(1280, 820)
        self._scene = QGraphicsScene(self)
        self._canvas = EditorCanvas(self)
        self._canvas.setScene(self._scene)
        self._canvas.key_handler = self._move_selected_key
        self._canvas.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._canvas.setBackgroundBrush(QColor("#0f172a"))
        self._items: dict[str, EditableItem] = {}
        self._elements = {element.id: element for element in layout.elements}
        artwork = QGraphicsSvgItem(str(layout.svg))
        artwork.setZValue(-10)
        self._scene.addItem(artwork)
        self._bounds = artwork.boundingRect()
        self._scene.setSceneRect(self._bounds)
        for element in layout.elements:
            mapped = self._map_to_scene(element)
            item = EditableItem(mapped)
            self._items[element.id] = item
            self._scene.addItem(item)
        self._scene.selectionChanged.connect(self._show_selection)

        root = QHBoxLayout(self)
        root.addWidget(self._canvas, 1)
        side_frame = QFrame()
        side_frame.setFixedWidth(280)
        side = QVBoxLayout(side_frame)
        side.addWidget(QLabel("Editor de layout"))
        instructions = QLabel("Arrastre: recorrido grande. Flechas: 0.25 unidades. Mayús+flechas: 2 unidades.")
        instructions.setWordWrap(True)
        side.addWidget(instructions)
        form = QFormLayout()
        self._id = QLabel("—")
        self._kind = QLabel("—")
        self._signal = QLabel("—")
        self._position = QLabel("—")
        form.addRow("Id", self._id)
        form.addRow("Tipo", self._kind)
        form.addRow("Señal", self._signal)
        form.addRow("Posición", self._position)
        side.addLayout(form)
        add_led = QPushButton("+ LED")
        add_led.clicked.connect(lambda: self._add_component("led"))
        side.addWidget(add_led)
        add_switch = QPushButton("+ Switch")
        add_switch.clicked.connect(lambda: self._add_component("button"))
        side.addWidget(add_switch)
        color = QPushButton("Cambiar color")
        color.clicked.connect(self._change_color)
        side.addWidget(color)
        delete = QPushButton("Eliminar seleccionado")
        delete.clicked.connect(self._delete_selected)
        side.addWidget(delete)
        fit = QPushButton("Ajustar al lienzo")
        fit.clicked.connect(self.fit_to_canvas)
        side.addWidget(fit)
        save = QPushButton("Guardar JSON")
        save.clicked.connect(self.save)
        side.addWidget(save)
        side.addStretch()
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        side.addWidget(close)
        root.addWidget(side_frame)
        QTimer.singleShot(0, self._prepare_canvas)

    def _map_to_scene(self, element: BoardLayoutElement) -> BoardLayoutElement:
        origin_x, origin_y, width, height = self._layout.view_box
        return BoardLayoutElement(
            element.id, element.kind, element.signal,
            self._bounds.x() + (element.x - origin_x) * self._bounds.width() / width,
            self._bounds.y() + (element.y - origin_y) * self._bounds.height() / height,
            element.width * self._bounds.width() / width,
            element.height * self._bounds.height() / height,
            element.color,
        )

    def _map_to_layout(self, item: EditableItem) -> tuple[float, float]:
        origin_x, origin_y, width, height = self._layout.view_box
        rect = item.sceneBoundingRect()
        return (
            round(origin_x + (rect.x() - self._bounds.x()) * width / self._bounds.width(), 3),
            round(origin_y + (rect.y() - self._bounds.y()) * height / self._bounds.height(), 3),
        )

    def _add_component(self, kind: str) -> None:
        prefix = "LED" if kind == "led" else "SW"
        element_id, ok = QInputDialog.getText(self, "Nuevo componente", "Identificador", text=f"{prefix}{len(self._elements)}")
        if not ok or not element_id or element_id in self._elements: return
        signal, ok = QInputDialog.getText(self, "Nuevo componente", "Señal HDL", text=element_id)
        if not ok or not signal: return
        width, height = (4.2, 1.8) if kind == "led" else (14.0, 5.6)
        element = BoardLayoutElement(element_id, kind, signal, self._layout.view_box[2] / 2 - width / 2, self._layout.view_box[3] / 2 - height / 2, width, height, "#b6ff00")
        self._elements[element_id] = element
        item = EditableItem(self._map_to_scene(element)); self._items[element_id] = item; self._scene.addItem(item); item.setSelected(True)

    def _delete_selected(self) -> None:
        selected = self._scene.selectedItems()
        if selected:
            item = selected[0]; self._scene.removeItem(item); self._items.pop(item.element_id, None); self._elements.pop(item.element_id, None)

    def _change_color(self) -> None:
        selected = self._scene.selectedItems()
        if not selected: return
        item = selected[0]; element = self._elements[item.element_id]
        color = QColorDialog.getColor(QColor(element.color), self, "Color del componente")
        if color.isValid():
            self._elements[element.id] = BoardLayoutElement(element.id, element.kind, element.signal, element.x, element.y, element.width, element.height, color.name())

    def _show_selection(self) -> None:
        selected = self._scene.selectedItems()
        if not selected:
            self._id.setText("—"); self._kind.setText("—"); self._signal.setText("—"); self._position.setText("—")
            return
        item = selected[0]
        source = self._elements[item.element_id]
        x, y = self._map_to_layout(item)
        self._id.setText(source.id); self._kind.setText(source.kind); self._signal.setText(source.signal)
        self._position.setText(f"x={x}, y={y}")

    def _prepare_canvas(self) -> None:
        self.fit_to_canvas()
        self._canvas.setFocus()

    def _move_selected_key(self, event) -> bool:
        selected = self._scene.selectedItems()
        arrows = {
            Qt.Key.Key_Left: (-1, 0), Qt.Key.Key_Right: (1, 0),
            Qt.Key.Key_Up: (0, -1), Qt.Key.Key_Down: (0, 1),
        }
        if selected and event.key() in arrows:
            step = 2.0 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 0.25
            dx, dy = arrows[event.key()]
            item = selected[0]
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                rect = item.rect()
                item.setRect(rect.x(), rect.y(), max(0.25, rect.width() + dx * step), max(0.25, rect.height() + dy * step))
            else:
                item.moveBy(dx * step, dy * step)
            self._show_selection()
            return True
        return False

    def fit_to_canvas(self) -> None:
        self._canvas.fitInView(self._bounds, Qt.AspectRatioMode.KeepAspectRatio)

    def save(self) -> None:
        raw = json.loads(self._layout.source.read_text(encoding="utf-8"))
        original = {component["id"]: component for component in raw["components"]}
        raw["components"] = []
        for element_id, item in self._items.items():
            x, y = self._map_to_layout(item); rect = item.sceneBoundingRect(); element = self._elements[element_id]
            component = original.get(element_id, {})
            component.update({"id": element_id, "type": element.kind, "signal": element.signal, "x": x, "y": y, "width": round(rect.width(), 3), "height": round(rect.height(), 3), "color": element.color})
            raw["components"].append(component)
        self._layout.source.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
        self.accept()
