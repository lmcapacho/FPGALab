"""Non-electrical, Lab-local workbench annotations."""

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QAbstractTextDocumentLayout, QFont, QPainter, QPalette, QPen, QTextDocument
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsRectItem

from ..i18n import t
from ..theme import color


class WorkbenchAnnotationItem(QGraphicsRectItem):
    def __init__(self, data, edit):
        self.data = data
        self._edit = edit
        self._editable = True
        self._dirty = False
        self._drag_handle = None
        self._fixed_endpoint = None
        super().__init__(QRectF(0, 0, max(12, float(data.get("width", 160))), max(12, float(data.get("height", 64)))))
        self.setPos(*data.get("position", [0, 0]))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self.setZValue(-1)
        self.setToolTip(t("Drag an endpoint to change the line. Hold Shift for horizontal or vertical.") if data.get("type") == "line" else (data.get("text", "") if data.get("type") == "text" else data.get("type", "")))

    def set_editable(self, enabled):
        self._editable = enabled
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, enabled)

    def boundingRect(self):
        return self.rect().adjusted(-6, -6, 6, 6)

    def hoverMoveEvent(self, event):
        self.setCursor(Qt.CursorShape.SizeFDiagCursor if self._handle_at(event.pos()) is not None else Qt.CursorShape.ArrowCursor)
        super().hoverMoveEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self._editable:
            self._dirty = True
        return super().itemChange(change, value)

    def take_position_update(self):
        if not self._dirty:
            return None
        self._dirty = False
        return (self.data["id"], self.pos().x(), self.pos().y(),
                self.rect().width(), self.rect().height(), bool(self.data.get("reverse", False)),
                self.data.get("orientation", "free"))

    def _endpoints(self):
        rect = self.rect()
        if self.data.get("orientation") == "horizontal":
            return QPointF(rect.left(), rect.center().y()), QPointF(rect.right(), rect.center().y())
        if self.data.get("orientation") == "vertical":
            return QPointF(rect.center().x(), rect.top()), QPointF(rect.center().x(), rect.bottom())
        return (rect.bottomLeft(), rect.topRight()) if self.data.get("reverse", False) else (rect.topLeft(), rect.bottomRight())

    def _handle_at(self, point):
        if not self._editable or not self.isSelected():
            return None
        handles = self._endpoints() if self.data.get("type") == "line" else (self.rect().bottomRight(),)
        for index, handle in enumerate(handles):
            if (point - handle).manhattanLength() <= 14:
                return index
        return None

    def resize_handle_at(self, scene_point):
        return self._handle_at(self.mapFromScene(scene_point)) is not None

    def mousePressEvent(self, event):
        handle = self._handle_at(event.pos()) if event.button() == Qt.MouseButton.LeftButton else None
        if handle is not None:
            self._drag_handle = handle
            self._fixed_endpoint = self.mapToScene(self._endpoints()[1 - handle]) if self.data.get("type") == "line" else None
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_handle is None:
            super().mouseMoveEvent(event)
            return
        if self.data.get("type") == "line":
            target = event.scenePos()
            fixed = self._fixed_endpoint
            dx, dy = target.x() - fixed.x(), target.y() - fixed.y()
            orientation = "free"
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                orientation = "horizontal" if abs(dx) >= abs(dy) else "vertical"
            self.data["orientation"] = orientation
            if orientation == "horizontal":
                self.setPos(min(target.x(), fixed.x()), fixed.y() - 6)
                self.setRect(0, 0, max(12, abs(dx)), 12)
            elif orientation == "vertical":
                self.setPos(fixed.x() - 6, min(target.y(), fixed.y()))
                self.setRect(0, 0, 12, max(12, abs(dy)))
            else:
                self.setPos(min(target.x(), fixed.x()), min(target.y(), fixed.y()))
                self.setRect(0, 0, max(12, abs(dx)), max(12, abs(dy)))
                self.data["reverse"] = dx * dy < 0
        else:
            width, height = max(24, event.pos().x()), max(24, event.pos().y())
            if self.data.get("type") == "ellipse" and event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                width = height = max(width, height)
            self.setRect(0, 0, width, height)
        self._dirty = True
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._drag_handle is not None:
            self._drag_handle = None
            self._fixed_endpoint = None
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, self._editable)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self._editable and self.data.get("type") == "text":
            self._edit(self.data)
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def paint(self, painter: QPainter, option, widget=None):
        del option, widget
        kind = self.data.get("type", "text")
        pen = QPen(color("accent") if self.isSelected() else color("border_strong"), 2)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        rect = self.rect().adjusted(2, 2, -2, -2)
        if kind == "rectangle":
            painter.drawRoundedRect(rect, 5, 5)
        elif kind == "ellipse":
            painter.drawEllipse(rect)
        elif kind == "line":
            painter.drawLine(*self._endpoints())
        else:
            document = QTextDocument()
            font = QFont()
            font.setPointSize(12)
            document.setDefaultFont(font)
            document.setDocumentMargin(0)
            document.setMarkdown(self.data.get("text", ""))
            document.setTextWidth(rect.width())
            painter.save()
            painter.setClipRect(rect)
            painter.translate(rect.topLeft())
            context = QAbstractTextDocumentLayout.PaintContext()
            context.palette.setColor(QPalette.ColorRole.Text, color("text"))
            document.documentLayout().draw(painter, context)
            painter.restore()
            if self.isSelected():
                painter.setPen(pen)
                painter.drawRect(rect)
        if self.isSelected() and self._editable:
            painter.setBrush(color("accent"))
            for handle in (self._endpoints() if kind == "line" else (self.rect().bottomRight(),)):
                painter.drawEllipse(handle, 4, 4)
