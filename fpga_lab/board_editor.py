"""Minimal position editor for SVG board layouts."""

from __future__ import annotations

import json
import shutil
from dataclasses import replace

from PyQt6.QtCore import QSettings, QTimer, Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtSvgWidgets import QGraphicsSvgItem
from PyQt6.QtWidgets import (
    QColorDialog, QDialog, QDialogButtonBox, QFormLayout, QFrame, QInputDialog, QGraphicsItem, QGraphicsRectItem,
    QCheckBox, QComboBox, QGraphicsScene, QGraphicsView, QHBoxLayout, QLabel, QMessageBox, QPushButton, QScrollArea, QSplitter, QVBoxLayout, QWidget,
)

from .board_layout import BoardLayout, BoardLayoutElement
from .board import BoardDefinition
from .i18n import t
from .theme import Metrics, color, style_button


class EditableItem(QGraphicsRectItem):
    def __init__(self, element: BoardLayoutElement):
        super().__init__(element.x, element.y, element.width, element.height)
        self.element_id = element.id
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def paint(self, painter: QPainter, _option, _widget=None) -> None:
        painter.setPen(QPen(color("danger") if self.isSelected() else color("warning"), 0.65))
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
        definition_path = layout.source.parent / "board.json"
        self._board = BoardDefinition.load(definition_path) if definition_path.is_file() else None
        self.setWindowTitle(t("Edit layout · {board}", board=layout.board_id))
        self.setWindowFlag(Qt.WindowType.Window, True)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)
        self.setMinimumSize(900, 600)
        self.resize(1280, 820)
        settings = QSettings("FPGALab", "FPGALab")
        geometry = settings.value("windows/board_layout_editor/geometry")
        if geometry:
            self.restoreGeometry(geometry)
        self._scene = QGraphicsScene(self)
        self._canvas = EditorCanvas(self)
        self._canvas.setScene(self._scene)
        self._canvas.key_handler = self._move_selected_key
        self._canvas.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._canvas.setBackgroundBrush(color("canvas"))
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
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.setObjectName("layoutEditorSplitter")
        splitter.addWidget(self._canvas)
        side_frame = QFrame()
        side_frame.setMinimumWidth(300)
        side_frame.setMaximumWidth(420)
        side = QVBoxLayout(side_frame)
        contents = QWidget()
        contents.setObjectName("layoutEditorContents")
        sections = QVBoxLayout(contents)
        sections.setContentsMargins(0, 0, Metrics.SPACE_MD, 0)
        sections.setSpacing(Metrics.SPACE_MD)
        scroll = QScrollArea()
        scroll.setObjectName("layoutEditorScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(contents)
        side.addWidget(scroll)

        def heading(text: str) -> None:
            label = QLabel(text)
            font = label.font()
            font.setBold(True)
            label.setFont(font)
            sections.addWidget(label)

        heading(t("Selected component"))
        self._selection_hint = QLabel(t("Select a component on the board to edit its properties."))
        self._selection_hint.setObjectName("caption")
        self._selection_hint.setWordWrap(True)
        sections.addWidget(self._selection_hint)
        form = QFormLayout()
        self._id = QLabel("—")
        self._kind = QLabel("—")
        self._signal = QComboBox()
        self._signal.setEnabled(False)
        self._signal.setToolTip(t("Logical board signal, not a physical FPGA pin number or the project's HDL net name."))
        self._signal.currentTextChanged.connect(self._change_signal)
        self._position = QLabel("—")
        form.addRow("Id", self._id)
        form.addRow(t("Type"), self._kind)
        self._signal_label = QLabel(t("Board signal"))
        form.addRow(self._signal_label, self._signal)
        form.addRow(t("Position"), self._position)
        self._role = QComboBox()
        self._role.setEnabled(False)
        self._role.currentIndexChanged.connect(self._change_role)
        form.addRow(t("Role"), self._role)
        sections.addLayout(form)
        component_actions = QHBoxLayout()
        self._color_button = QPushButton(t("Change color"))
        self._color_button.setEnabled(False)
        self._color_button.clicked.connect(self._change_color)
        component_actions.addWidget(self._color_button)
        self._delete_button = QPushButton(t("Delete selected"))
        self._delete_button.setEnabled(False)
        style_button(self._delete_button, "danger")
        self._delete_button.clicked.connect(self._delete_selected)
        component_actions.addWidget(self._delete_button)
        sections.addLayout(component_actions)
        sections.addSpacing(Metrics.SPACE_MD)
        heading(t("Add components"))
        add_actions = QHBoxLayout()
        add_led = QPushButton(t("Add LED"))
        add_led.clicked.connect(lambda: self._add_component("led"))
        add_actions.addWidget(add_led)
        add_switch = QPushButton(t("Add button"))
        add_switch.clicked.connect(lambda: self._add_component("button"))
        add_actions.addWidget(add_switch)
        sections.addLayout(add_actions)
        sections.addSpacing(Metrics.SPACE_MD)
        heading(t("Board appearance"))
        transform_hint = QLabel(t("Rotation and mirroring apply to the whole board in the main window."))
        transform_hint.setObjectName("caption")
        transform_hint.setWordWrap(True)
        sections.addWidget(transform_hint)
        transform_form = QFormLayout()
        self._rotation = QComboBox()
        self._rotation.addItems(("0°", "90°", "180°", "270°"))
        self._rotation.setCurrentIndex(self._layout.rotation // 90)
        self._mirror_x = QCheckBox(t("Mirror horizontally"))
        self._mirror_x.setChecked(self._layout.mirror_x)
        self._mirror_y = QCheckBox(t("Mirror vertically"))
        self._mirror_y.setChecked(self._layout.mirror_y)
        transform_form.addRow(t("Rotation"), self._rotation)
        transform_form.addRow(self._mirror_x)
        transform_form.addRow(self._mirror_y)
        sections.addLayout(transform_form)
        sections.addSpacing(Metrics.SPACE_MD)
        heading(t("Editor view"))
        fit = QPushButton(t("Fit canvas"))
        fit.clicked.connect(self.fit_to_canvas)
        sections.addWidget(fit)
        instructions = QLabel(t("Drag for larger moves. Arrows: 0.25 units. Shift+arrows: 2 units."))
        instructions.setObjectName("caption")
        instructions.setWordWrap(True)
        sections.addWidget(instructions)
        sections.addStretch()
        footer = QHBoxLayout()
        save = QPushButton(t("Save layout"))
        style_button(save, "primary")
        save.clicked.connect(self.save)
        footer.addWidget(save, 1)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        footer.addWidget(close)
        side.addLayout(footer)
        splitter.addWidget(side_frame)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([900, 340])
        root.addWidget(splitter)
        QTimer.singleShot(0, self._prepare_canvas)

    def closeEvent(self, event) -> None:
        settings = QSettings("FPGALab", "FPGALab")
        settings.setValue("windows/board_layout_editor/geometry", self.saveGeometry())
        super().closeEvent(event)

    def _map_to_scene(self, element: BoardLayoutElement) -> BoardLayoutElement:
        origin_x, origin_y, width, height = self._layout.view_box
        return BoardLayoutElement(
            element.id, element.kind, element.signal,
            self._bounds.x() + (element.x - origin_x) * self._bounds.width() / width,
            self._bounds.y() + (element.y - origin_y) * self._bounds.height() / height,
            element.width * self._bounds.width() / width,
            element.height * self._bounds.height() / height,
            element.color,
            element.role,
        )

    def _map_to_layout(self, item: EditableItem) -> tuple[float, float]:
        origin_x, origin_y, width, height = self._layout.view_box
        rect = item.sceneBoundingRect()
        return (
            round(origin_x + (rect.x() - self._bounds.x()) * width / self._bounds.width(), 3),
            round(origin_y + (rect.y() - self._bounds.y()) * height / self._bounds.height(), 3),
        )

    def _add_component(self, kind: str) -> None:
        roles = [(t("No special role"), None),
                 (t("Power indicator"), "power") if kind == "led" else (t("Reset button"), "reset")]
        choice, ok = QInputDialog.getItem(self, t("New component"), t("Role"),
                                        [label for label, _role in roles], editable=False)
        if not ok:
            return
        role = next(role for label, role in roles if label == choice)
        prefix = "LED" if kind == "led" else "SW"
        default_signal = "PWR" if role == "power" else "RESET" if role == "reset" else None
        default_id = default_signal or f"{prefix}{len(self._elements)}"
        if default_id in self._elements:
            index = 1
            while f"{default_id}_{index}" in self._elements:
                index += 1
            default_id = f"{default_id}_{index}"
        element_id, ok = QInputDialog.getText(self, t("New component"), t("Identifier"), text=default_id)
        element_id = element_id.strip()
        if not ok or not element_id or element_id in self._elements: return
        signals = self._board_signals(kind)
        if role is not None:
            signal, ok = QInputDialog.getText(self, t("New component"), t("Internal signal"), text=default_signal)
        elif self._board is not None:
            if not signals:
                return
            signal, ok = QInputDialog.getItem(self, t("New component"), t("Board signal"), signals, editable=False)
        else:
            signal, ok = QInputDialog.getText(self, t("New component"), t("Board signal"), text=element_id)
        signal = signal.strip()
        if not ok or not signal: return
        width, height = (4.2, 1.8) if kind == "led" else (14.0, 5.6)
        element = BoardLayoutElement(element_id, kind, signal, self._layout.view_box[2] / 2 - width / 2, self._layout.view_box[3] / 2 - height / 2, width, height, "#b6ff00", role)
        if role is not None:
            for other_id, other in self._elements.items():
                if other.role == role:
                    self._elements[other_id] = replace(other, role=None)
        self._elements[element_id] = element
        self._scene.clearSelection()
        item = EditableItem(self._map_to_scene(element)); self._items[element_id] = item; self._scene.addItem(item); item.setSelected(True)

    def _delete_selected(self) -> None:
        selected = self._scene.selectedItems()
        if selected:
            item = selected[0]; self._scene.removeItem(item); self._items.pop(item.element_id, None); self._elements.pop(item.element_id, None)

    def _change_color(self) -> None:
        selected = self._scene.selectedItems()
        if not selected: return
        item = selected[0]; element = self._elements[item.element_id]
        color = QColorDialog.getColor(QColor(element.color), self, t("Component color"))
        if color.isValid():
            self._elements[element.id] = replace(element, color=color.name())

    def _change_role(self) -> None:
        selected = self._scene.selectedItems()
        if not selected:
            return
        element_id = selected[0].element_id
        role = self._role.currentData()
        if role is not None:
            for other_id, element in self._elements.items():
                if other_id != element_id and element.role == role:
                    self._elements[other_id] = replace(element, role=None)
        self._elements[element_id] = replace(self._elements[element_id], role=role)
        self._populate_signals(self._elements[element_id])

    def _board_signals(self, kind: str) -> list[str]:
        if self._board is None:
            return []
        direction = "output" if kind == "led" else "input"
        return [pin.id for pin in self._board.pins
                if pin.direction in {direction, "inout"} and pin.id != self._board.clock_endpoint]

    def _populate_signals(self, element: BoardLayoutElement) -> None:
        self._signal.blockSignals(True)
        self._signal.clear()
        internal = element.role is not None or self._board is None
        self._signal_label.setText(t("Internal signal") if element.role is not None else t("Board signal"))
        self._signal.setEditable(internal)
        for signal in self._board_signals(element.kind):
            self._signal.addItem(signal, signal)
        index = self._signal.findData(element.signal)
        if index < 0:
            label = element.signal if internal else t("{signal} (unavailable)", signal=element.signal)
            self._signal.addItem(label, element.signal)
            index = self._signal.count() - 1
        self._signal.setCurrentIndex(index)
        self._signal.setToolTip(t("Internal identifier for the selected role; no FPGA pin is required.") if element.role is not None else
                               t("Logical board signal, not a physical FPGA pin number or the project's HDL net name.")
                               if internal or element.signal in self._board_signals(element.kind)
                               else t("This signal is not available for this control. Its saved value is preserved."))
        self._signal.blockSignals(False)

    def _change_signal(self, text: str) -> None:
        selected = self._scene.selectedItems()
        if selected:
            element_id = selected[0].element_id
            signal = text if self._signal.isEditable() else self._signal.currentData()
            self._elements[element_id] = replace(self._elements[element_id], signal=(signal or "").strip())

    def _show_selection(self) -> None:
        selected = self._scene.selectedItems()
        self._selection_hint.setVisible(not selected)
        self._color_button.setEnabled(bool(selected) and self._elements[selected[0].element_id].kind == "led")
        self._delete_button.setEnabled(bool(selected))
        if not selected:
            self._signal_label.setText(t("Board signal"))
            self._id.setText("—"); self._kind.setText("—"); self._signal.clear(); self._position.setText("—")
            self._signal.setEnabled(False)
            self._role.setEnabled(False)
            self._role.clear()
            return
        item = selected[0]
        source = self._elements[item.element_id]
        x, y = self._map_to_layout(item)
        self._id.setText(source.id); self._kind.setText(source.kind)
        self._populate_signals(source)
        self._signal.setEnabled(True)
        self._position.setText(f"x={x}, y={y}")
        self._role.blockSignals(True)
        self._role.clear()
        self._role.addItem(t("No special role"), None)
        if source.kind == "led":
            self._role.addItem(t("Power indicator"), "power")
        elif source.kind == "button":
            self._role.addItem(t("Reset button"), "reset")
        self._role.setCurrentIndex(max(0, self._role.findData(source.role)))
        self._role.setEnabled(True)
        self._role.blockSignals(False)

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

    def refresh_theme(self) -> None:
        """Refresh custom canvas colors after a live palette switch."""
        self._canvas.setBackgroundBrush(color("canvas"))
        self._scene.update()
        self._canvas.viewport().update()

    def fit_to_canvas(self) -> None:
        self._canvas.fitInView(self._bounds, Qt.AspectRatioMode.KeepAspectRatio)

    def save(self) -> None:
        if any(not element.signal for element in self._elements.values()):
            QMessageBox.warning(self, t("Save board layout"), t("Each layout component must have a signal."))
            return
        replace(self._layout, elements=tuple(self._elements.values())).validate()
        prompt = t(
            "This changes the packaged board layout used by FPGALab. "
            "Continue and keep a backup of the previous layout?"
        )
        if QMessageBox.question(
            self, t("Save board layout"), prompt,
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        ) != QMessageBox.StandardButton.Save:
            return
        raw = json.loads(self._layout.source.read_text(encoding="utf-8"))
        original = {component["id"]: component for component in raw["components"]}
        raw["components"] = []
        for element_id, item in self._items.items():
            x, y = self._map_to_layout(item); rect = item.sceneBoundingRect(); element = self._elements[element_id]
            component = original.get(element_id, {})
            component.update({"id": element_id, "type": element.kind, "signal": element.signal, "x": x, "y": y, "width": round(rect.width(), 3), "height": round(rect.height(), 3), "color": element.color})
            if element.role is None:
                component.pop("role", None)
            else:
                component["role"] = element.role
            raw["components"].append(component)
        raw["transform"] = {
            "rotation": self._rotation.currentIndex() * 90,
            "mirror_x": self._mirror_x.isChecked(),
            "mirror_y": self._mirror_y.isChecked(),
        }
        backup = self._layout.source.with_suffix(self._layout.source.suffix + ".bak")
        shutil.copy2(self._layout.source, backup)
        self._layout.source.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
        self.accept()
