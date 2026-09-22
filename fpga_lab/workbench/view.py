"""Zoomable and editable graphics view for peripheral layouts."""

from __future__ import annotations

from PyQt6.QtCore import QPointF, Qt, pyqtSignal
from PyQt6.QtWidgets import QGraphicsView

from .item import WorkbenchPeripheralItem
from .annotation import WorkbenchAnnotationItem


class WorkbenchView(QGraphicsView):
    """Zoomable, pannable workbench canvas with keyboard editing actions."""

    zoom_changed = pyqtSignal(float)
    camera_changed = pyqtSignal(QPointF)
    _CANVAS_EXTENT = 100_000.0

    def __init__(self, scene, delete_selected, duplicate_selected, persist_positions, undo, redo, parent=None):
        super().__init__(scene, parent)
        self._delete_selected = delete_selected
        self._duplicate_selected = duplicate_selected
        self._persist_positions = persist_positions
        self._undo = undo
        self._redo = redo
        self._zoom = 1.0
        self._panning = False
        self._pan_paused = False
        self._pan_button = None
        self._pan_start = QPointF()
        self._pan_center = QPointF()
        self._editing_enabled = True
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.ensure_scene_fits()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.ensure_scene_fits()

    def ensure_scene_fits(self) -> None:
        """Maintain a large symmetric canvas without exposing scroll bars."""
        extent = self._CANVAS_EXTENT
        self.scene().setSceneRect(-extent, -extent, extent * 2, extent * 2)

    def camera_center(self) -> QPointF:
        """Return the scene coordinate currently centered in the viewport."""
        return self.mapToScene(self.viewport().rect().center())

    def restore_camera(self, center: QPointF | None = None) -> None:
        """Restore a saved camera or center the initial collection of parts."""
        if center is None:
            bounds = self.scene().itemsBoundingRect()
            center = bounds.center() if not bounds.isEmpty() else QPointF(0.0, 0.0)
        self.centerOn(center)

    def mousePressEvent(self, event):
        self.setFocus()
        if (
            self._editing_enabled
            and event.button() == Qt.MouseButton.LeftButton
            and event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        ):
            item = self.itemAt(event.position().toPoint())
            if isinstance(item, (WorkbenchPeripheralItem, WorkbenchAnnotationItem)):
                resizing = isinstance(item, WorkbenchAnnotationItem) and item.resize_handle_at(
                    self.mapToScene(event.position().toPoint())
                )
                if not resizing:
                    item.setSelected(not item.isSelected())
                    event.accept()
                    return
        wants_pan = event.button() == Qt.MouseButton.MiddleButton or (
            event.button() == Qt.MouseButton.LeftButton
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        )
        if wants_pan:
            self._panning = True
            self._pan_paused = False
            self._pan_button = event.button()
            self._pan_start = event.position()
            self._pan_center = self.camera_center()
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self._set_canvas_cursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._panning and event.button() == self._pan_button:
            self._panning = False
            self._pan_paused = False
            self._pan_button = None
            self.setDragMode(
                QGraphicsView.DragMode.RubberBandDrag
                if self._editing_enabled else QGraphicsView.DragMode.NoDrag
            )
            self._set_canvas_cursor(Qt.CursorShape.ArrowCursor)
            self.camera_changed.emit(self.camera_center())
            event.accept()
            return
        super().mouseReleaseEvent(event)
        if self._editing_enabled and event.button() == Qt.MouseButton.LeftButton:
            updates = [
                update
                for item in self.scene().items()
                if isinstance(item, (WorkbenchPeripheralItem, WorkbenchAnnotationItem))
                if (update := item.take_position_update()) is not None
            ]
            if updates:
                self._persist_positions(updates)

    def _set_canvas_cursor(self, shape: Qt.CursorShape) -> None:
        """Keep the view and its viewport cursor synchronized."""
        self.setCursor(shape)
        self.viewport().setCursor(shape)

    def mouseMoveEvent(self, event):
        inside = self.viewport().rect().contains(event.position().toPoint())
        grabbed_item = self.scene().mouseGrabberItem()
        if not inside and (self._panning or isinstance(grabbed_item, (WorkbenchPeripheralItem, WorkbenchAnnotationItem))):
            self._pan_paused = self._panning
            event.accept()
            return
        if self._panning:
            if self._pan_paused:
                self._pan_start = event.position()
                self._pan_center = self.camera_center()
                self._pan_paused = False
                event.accept()
                return
            delta = event.position() - self._pan_start
            self.centerOn(self._pan_center - QPointF(delta.x() / self._zoom, delta.y() / self._zoom))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def wheelEvent(self, event):
        """Use the wheel exclusively for cursor-centered canvas zoom."""
        delta = event.angleDelta().y() or event.angleDelta().x()
        steps = delta / 120
        if steps:
            self.set_zoom(self._zoom * (1.15 ** steps))
        event.accept()

    def set_zoom(self, zoom: float) -> None:
        """Apply bounded cursor-anchored zoom independently of canvas size."""
        zoom = max(0.1, min(float(zoom), 2.5))
        if abs(zoom - self._zoom) < 0.001:
            return
        self._zoom = zoom
        self.resetTransform()
        self.scale(self._zoom, self._zoom)
        self.zoom_changed.emit(self._zoom)
        self.camera_changed.emit(self.camera_center())

    def zoom_in(self) -> None:
        self.set_zoom(self._zoom * 1.15)

    def zoom_out(self) -> None:
        self.set_zoom(self._zoom / 1.15)

    def reset_zoom(self) -> None:
        self.set_zoom(1.0)

    def fit_contents(self) -> None:
        """Fit all workbench parts in the viewport using the regular persisted zoom."""
        bounds = self.scene().itemsBoundingRect()
        if bounds.isEmpty():
            self.reset_zoom()
            return
        margin = 24.0
        fitted = bounds.adjusted(-margin, -margin, margin, margin)
        viewport = self.viewport().size()
        if fitted.width() <= 0 or fitted.height() <= 0:
            return
        zoom = min(viewport.width() / fitted.width(), viewport.height() / fitted.height())
        self.set_zoom(zoom)
        self.centerOn(bounds.center())
        self.camera_changed.emit(self.camera_center())

    def set_editable(self, enabled: bool) -> None:
        """Allow navigation while blocking destructive keyboard actions."""
        self._editing_enabled = enabled
        if not self._panning:
            self.setDragMode(
                QGraphicsView.DragMode.RubberBandDrag
                if enabled else QGraphicsView.DragMode.NoDrag
            )

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_0 and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.reset_zoom()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Z and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._redo() if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else self._undo()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Y and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._redo()
            event.accept()
            return
        if (
            self._editing_enabled
            and event.key() == Qt.Key.Key_D
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            selected = [item.peripheral if isinstance(item, WorkbenchPeripheralItem) else item.data for item in self.scene().selectedItems() if isinstance(item, (WorkbenchPeripheralItem, WorkbenchAnnotationItem))]
            if selected:
                self._duplicate_selected(selected)
                event.accept()
                return
        if self._editing_enabled and event.key() in {Qt.Key.Key_Delete, Qt.Key.Key_Backspace}:
            selected = [item.peripheral if isinstance(item, WorkbenchPeripheralItem) else item.data for item in self.scene().selectedItems() if isinstance(item, (WorkbenchPeripheralItem, WorkbenchAnnotationItem))]
            if selected:
                self._delete_selected(selected)
                event.accept()
                return
        super().keyPressEvent(event)
