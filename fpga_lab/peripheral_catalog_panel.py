"""Searchable overlay catalog built entirely from peripheral manifests."""

from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QKeyEvent
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from .i18n import language_manager, t
from .peripherals.catalog import icon_path_for
from .peripherals.manifest import PeripheralSpec
from .theme import Metrics, style_button


_CATEGORY_ORDER = ("input", "output", "display", "audio", "video", "logic")
_CATEGORY_LABELS = {
    "input": "Input",
    "output": "Output",
    "display": "Display",
    "audio": "Audio",
    "video": "Video",
    "logic": "Logic",
}


def matches_catalog_spec(
    spec: PeripheralSpec,
    query: str = "",
    category: str | None = None,
) -> bool:
    """Match translated metadata while retaining stable English keywords."""
    if category and spec.category != category:
        return False
    normalized_query = query.strip().casefold()
    if not normalized_query:
        return True
    haystack = " ".join((
        spec.id,
        t(spec.label),
        t(spec.description) if spec.description else "",
        spec.category,
        *spec.keywords,
    )).casefold()
    return normalized_query in haystack


class PeripheralCatalogPanel(QFrame):
    """Non-modal drawer for discovering and selecting manifest peripherals."""

    add_requested = pyqtSignal(str)

    def __init__(self, specs: dict[str, PeripheralSpec], parent=None):
        super().__init__(parent)
        self.setObjectName("catalogDrawer")
        self._specs = dict(specs)
        self._open = False
        self._closing = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Metrics.SPACE_LG, Metrics.SPACE_LG, Metrics.SPACE_LG, Metrics.SPACE_LG)
        layout.setSpacing(Metrics.SPACE_MD)
        header = QHBoxLayout()
        self._title = QLabel()
        self._title.setObjectName("drawerTitle")
        header.addWidget(self._title)
        header.addStretch(1)
        self._close_button = QPushButton()
        style_button(self._close_button, "icon", "close")
        self._close_button.clicked.connect(self.close_drawer)
        header.addWidget(self._close_button)
        layout.addLayout(header)

        self._search = QLineEdit()
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._refresh_items)
        layout.addWidget(self._search)

        self._category = QComboBox()
        self._category.currentIndexChanged.connect(self._refresh_items)
        layout.addWidget(self._category)

        self._list = QListWidget()
        self._list.setObjectName("catalogList")
        self._list.setIconSize(QSize(34, 34))
        self._list.itemDoubleClicked.connect(lambda _item: self._add_selected())
        self._list.itemSelectionChanged.connect(self._update_add_action)
        layout.addWidget(self._list, 1)

        self._add_button = QPushButton()
        style_button(self._add_button, "primary")
        self._add_button.clicked.connect(self._add_selected)
        layout.addWidget(self._add_button)

        self._animation = QPropertyAnimation(self, b"geometry", self)
        self._animation.setDuration(180)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.finished.connect(self._animation_finished)
        language_manager.language_changed.connect(self.retranslate_ui)
        self.retranslate_ui()
        self.hide()

    def retranslate_ui(self) -> None:
        """Refresh contributor-facing metadata using the active locale."""
        selected_category = self._category.currentData()
        self._title.setText(t("Add peripheral"))
        self._search.setPlaceholderText(t("Search peripherals…"))
        self._close_button.setToolTip(t("Close peripheral catalog"))
        self._close_button.setAccessibleName(t("Close peripheral catalog"))
        self._add_button.setText(t("Add selected peripheral"))
        self._category.blockSignals(True)
        self._category.clear()
        self._category.addItem(t("All categories"), None)
        for category in self.categories():
            self._category.addItem(t(_CATEGORY_LABELS.get(category, category.title())), category)
        index = self._category.findData(selected_category)
        self._category.setCurrentIndex(max(0, index))
        self._category.blockSignals(False)
        self._refresh_items()

    def categories(self) -> tuple[str, ...]:
        """Return stable built-in ordering followed by contributor categories."""
        available = {spec.category for spec in self._specs.values()}
        ordered = [category for category in _CATEGORY_ORDER if category in available]
        return tuple(ordered + sorted(available - set(ordered)))

    def matching_ids(self) -> tuple[str, ...]:
        """Expose filtered identifiers for behavior tests and keyboard workflows."""
        return tuple(self._list.item(index).data(Qt.ItemDataRole.UserRole) for index in range(self._list.count()))

    def _refresh_items(self) -> None:
        query = self._search.text().strip().casefold()
        category = self._category.currentData()
        current = self._list.currentItem().data(Qt.ItemDataRole.UserRole) if self._list.currentItem() else None
        self._list.clear()
        for spec in self._specs.values():
            if not matches_catalog_spec(spec, query, category):
                continue
            translated_label = t(spec.label)
            translated_description = t(spec.description) if spec.description else ""
            text = translated_label
            if translated_description:
                text += f"\n{translated_description}"
            item = QListWidgetItem(QIcon(str(icon_path_for(spec))), text)
            item.setData(Qt.ItemDataRole.UserRole, spec.id)
            item.setToolTip(translated_description or translated_label)
            item.setSizeHint(QSize(0, 58))
            self._list.addItem(item)
            if spec.id == current:
                self._list.setCurrentItem(item)
        if self._list.currentItem() is None and self._list.count():
            self._list.setCurrentRow(0)
        self._update_add_action()

    def _update_add_action(self) -> None:
        self._add_button.setEnabled(self._list.currentItem() is not None)

    def _add_selected(self) -> None:
        item = self._list.currentItem()
        if item is not None:
            self.add_requested.emit(str(item.data(Qt.ItemDataRole.UserRole)))

    def drawer_width(self) -> int:
        return min(390, max(300, round(self.parentWidget().width() * 0.42)))

    def target_geometry(self, visible: bool) -> QRect:
        parent = self.parentWidget()
        width = self.drawer_width()
        x = parent.width() - width if visible else parent.width()
        return QRect(x, 0, width, parent.height())

    def reposition(self) -> None:
        """Follow parent resizing without replaying the entrance animation."""
        if self.isVisible():
            self.setGeometry(self.target_geometry(not self._closing))

    def open_drawer(self) -> None:
        self._animation.stop()
        self._open = True
        self._closing = False
        self.setGeometry(self.target_geometry(False))
        self.show()
        self.raise_()
        self._animation.setStartValue(self.geometry())
        self._animation.setEndValue(self.target_geometry(True))
        self._animation.start()
        self._search.setFocus()

    def close_drawer(self) -> None:
        if not self.isVisible():
            return
        self._animation.stop()
        self._open = False
        self._closing = True
        self._animation.setStartValue(self.geometry())
        self._animation.setEndValue(self.target_geometry(False))
        self._animation.start()

    def toggle(self) -> None:
        self.close_drawer() if self._open else self.open_drawer()

    def _animation_finished(self) -> None:
        if self._closing:
            self.hide()
            self._closing = False
            parent = self.parentWidget()
            if hasattr(parent, "_position_catalog_button"):
                parent._position_catalog_button()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close_drawer()
            event.accept()
            return
        if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter} and self._list.hasFocus():
            self._add_selected()
            event.accept()
            return
        super().keyPressEvent(event)
