"""Icestudio design picker backed by a small recent-project history."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QVBoxLayout,
)

from .recent_projects import RecentProjects


class ProjectLauncherDialog(QDialog):
    """Select an Icestudio design before executing it through the cache."""

    def __init__(self, recent_projects: RecentProjects, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Abrir diseño Icestudio")
        self.setMinimumWidth(520)
        self._recent_projects = recent_projects
        self._selected_file: Path | None = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Seleccione el archivo .ice que desea ejecutar."))
        selected_layout = QHBoxLayout()
        self._path = QLineEdit()
        self._path.setReadOnly(True)
        browse = QPushButton("Examinar…")
        browse.clicked.connect(self._browse)
        selected_layout.addWidget(self._path, 1)
        selected_layout.addWidget(browse)
        layout.addLayout(selected_layout)

        layout.addWidget(QLabel("Diseños recientes"))
        self._recent_list = QListWidget()
        self._recent_list.itemSelectionChanged.connect(self._select_recent)
        self._recent_list.itemDoubleClicked.connect(lambda _: self.accept())
        layout.addWidget(self._recent_list, 1)
        self._load_recent()

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Ejecutar")
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)
        self._update_accept_button()

    @property
    def selected_file(self) -> Path | None:
        return self._selected_file

    def accept(self) -> None:
        if self._selected_file and self._selected_file.is_file():
            super().accept()

    def _load_recent(self) -> None:
        for path in self._recent_projects.paths():
            self._recent_list.addItem(str(path))

    def _browse(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar diseño Icestudio", "", "Diseños Icestudio (*.ice)"
        )
        if filename:
            self._set_selected(Path(filename))

    def _select_recent(self) -> None:
        item = self._recent_list.currentItem()
        if item:
            self._set_selected(Path(item.text()))

    def _set_selected(self, path: Path) -> None:
        self._selected_file = path.expanduser().resolve()
        self._path.setText(str(self._selected_file))
        self._update_accept_button()

    def _update_accept_button(self) -> None:
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(
            self._selected_file is not None and self._selected_file.is_file()
        )
