"""Zoomable and editable graphics view for peripheral layouts."""

from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QSettings, Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import QApplication, QGraphicsProxyWidget, QGraphicsView, QMenu

from .item import WorkbenchPeripheralItem
from .annotation import WorkbenchAnnotationItem
from ..theme import color
from ..i18n import t
from .clipboard import MIME_TYPE


class WorkbenchView(QGraphicsView):
    """Zoomable, pannable workbench canvas with keyboard editing actions."""

    zoom_changed = pyqtSignal(float)
    camera_changed = pyqtSignal(QPointF)
    copy_requested = pyqtSignal()
    paste_requested = pyqtSignal()
    _CANVAS_EXTENT = 100_000.0
    GRID_VISIBLE_KEY = "ui/workbench_grid_visible"
    GRID_SPACING = 20.0

    def __init__(self, scene, delete_selected, duplicate_selected, persist_positions, undo, redo, parent=None):
        super().__init__(scene, parent)
        self._delete_selected = delete_selected
        self._duplicate_selected = duplicate_selected
        self._persist_positions = persist_positions
        self._undo = undo
        self._redo = redo
        self._zoom = 1.0
        self._settings = QSettings("FPGALab", "FPGALab")
        self._grid_visible = self._settings.value(self.GRID_VISIBLE_KEY, False, type=bool)
        self._grid_snap = False
        self._grid_spacing = self.GRID_SPACING
        self._drag_anchor = None
        self._drag_origins = {}
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

    def set_grid_visible(self, visible: bool) -> None:
        """Persist a visual preference without modifying Lab data or positions."""
        self._grid_visible = bool(visible)
        self._settings.setValue(self.GRID_VISIBLE_KEY, self._grid_visible)
        self.viewport().update()

    def drawBackground(self, painter, rect) -> None:
        super().drawBackground(painter, rect)
        if not self._grid_visible:
            return
        visible = rect.intersected(self.mapToScene(self.viewport().rect()).boundingRect())
        spacing = self._grid_spacing
        while spacing * self._zoom < 12:
            spacing *= 2
        left, top = math.ceil(visible.left() / spacing), math.ceil(visible.top() / spacing)
        right, bottom = math.floor(visible.right() / spacing), math.floor(visible.bottom() / spacing)
        points = QPolygonF([QPointF(x * spacing, y * spacing)
                            for x in range(left, right + 1) for y in range(top, bottom + 1)])
        painter.save()
        pen = QPen(color("grid"), 2)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.drawPoints(points)
        painter.restore()

    def set_grid_snap(self, enabled: bool, spacing: float = GRID_SPACING) -> None:
        """Configure Lab editing without realigning existing elements."""
        self._grid_snap = bool(enabled)
        self._grid_spacing = spacing
        self.viewport().update()

    def _snap_drag(self) -> None:
        anchor = self._drag_anchor
        if not self._grid_snap or anchor is None or anchor.pos() == self._drag_origins[anchor]:
            return
        position = anchor.pos()
        spacing = self._grid_spacing
        target = QPointF(math.floor(position.x() / spacing + 0.5) * spacing,
                         math.floor(position.y() / spacing + 0.5) * spacing)
        offset = target - position
        for item in self._drag_origins:
            item.setPos(item.pos() + offset)

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
        self._drag_anchor = None
        self._drag_origins = {}
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
        anchor = self.scene().mouseGrabberItem()
        if self._editing_enabled and event.button() == Qt.MouseButton.LeftButton and isinstance(anchor, (WorkbenchPeripheralItem, WorkbenchAnnotationItem)):
            if not isinstance(anchor, WorkbenchAnnotationItem) or anchor._drag_handle is None:
                self._drag_anchor = anchor
                self._drag_origins = {item: QPointF(item.pos()) for item in self.scene().selectedItems()
                                      if isinstance(item, (WorkbenchPeripheralItem, WorkbenchAnnotationItem))}
                self._drag_origins.setdefault(anchor, QPointF(anchor.pos()))

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
        self._snap_drag()
        self._drag_anchor = None
        self._drag_origins = {}
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
        self._snap_drag()

    def wheelEvent(self, event):
        """Scroll an embedded monitor; otherwise zoom around the cursor."""
        hovered = self.itemAt(event.position().toPoint())
        if isinstance(hovered, QGraphicsProxyWidget) and hovered.widget() is not None and hovered.widget().property("scrollWheelContent"):
            super().wheelEvent(event)
            return
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
        if isinstance(self.scene().focusItem(), QGraphicsProxyWidget):
            super().keyPressEvent(event)
            return
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy_requested.emit()
            event.accept()
            return
        if self._editing_enabled and event.matches(QKeySequence.StandardKey.Paste):
            self.paste_requested.emit()
            event.accept()
            return
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

    def contextMenuEvent(self, event):
        hovered = self.itemAt(event.pos())
        if isinstance(hovered, QGraphicsProxyWidget):
            super().contextMenuEvent(event)
            return
        if isinstance(hovered, (WorkbenchPeripheralItem, WorkbenchAnnotationItem)) and not hovered.isSelected():
            self.scene().clearSelection()
            hovered.setSelected(True)
        menu = QMenu(self)
        copy_action = menu.addAction(t("Copy (Ctrl+C)"), self.copy_requested.emit)
        copy_action.setEnabled(any(isinstance(item, (WorkbenchPeripheralItem, WorkbenchAnnotationItem)) for item in self.scene().selectedItems()))
        paste_action = menu.addAction(t("Paste (Ctrl+V)"), self.paste_requested.emit)
        paste_action.setEnabled(self._editing_enabled and QApplication.clipboard().mimeData().hasFormat(MIME_TYPE))
        menu.exec(event.globalPos())
        menu.deleteLater()
        event.accept()
