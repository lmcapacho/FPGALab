"""Editor mínimo de posiciones para layouts de placas SVG."""

from __future__ import annotations

import json

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtSvgWidgets import QGraphicsSvgItem
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QFrame, QGraphicsItem, QGraphicsRectItem,
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
    """Permite ubicar componentes sobre el SVG y persistir sus coordenadas."""

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

    def _show_selection(self) -> None:
        selected = self._scene.selectedItems()
        if not selected:
            self._id.setText("—"); self._kind.setText("—"); self._signal.setText("—"); self._position.setText("—")
            return
        item = selected[0]
        source = next(element for element in self._layout.elements if element.id == item.element_id)
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
            selected[0].moveBy(dx * step, dy * step)
            self._show_selection()
            return True
        return False

    def fit_to_canvas(self) -> None:
        self._canvas.fitInView(self._bounds, Qt.AspectRatioMode.KeepAspectRatio)

    def save(self) -> None:
        raw = json.loads(self._layout.source.read_text(encoding="utf-8"))
        components = {component["id"]: component for component in raw["components"]}
        for element_id, item in self._items.items():
            x, y = self._map_to_layout(item)
            components[element_id]["x"] = x
            components[element_id]["y"] = y
        self._layout.source.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
        self.accept()
