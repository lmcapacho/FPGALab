"""Main application shell with an integrated Icestudio project bar."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from .lab_workspace import LabWorkspace
from .recent_projects import RecentProjects


class FPGALabMainWindow(QMainWindow):
    """Persistent shell that selects and hosts one active virtual laboratory."""

    project_requested = pyqtSignal(Path)
    stop_requested = pyqtSignal()

    def __init__(self, workspace: LabWorkspace, parent=None):
        super().__init__(parent)
        self.setWindowTitle("FPGALab · Laboratorio Virtual")
        self.setMinimumSize(1000, 680)
        self.setStyleSheet("""
            QMainWindow, QWidget { background:#0f172a; color:#e2e8f0; font-family:Inter,Arial,sans-serif; }
            QFrame#panel { background:#172033; border:1px solid #334155; border-radius:10px; }
            QLabel#caption { color:#94a3b8; font-size:11px; }
            QStatusBar { background:#172033; color:#fbbf24; border-top:1px solid #334155; font-weight:600; }
        """)
        self._recent_projects = RecentProjects()
        self._workspace = workspace
        self._selected_lab = self._workspace.ensure_default()
        self._lab_explicitly_selected = False
        self._active_lab: QWidget | None = None
        self._status_bar = QStatusBar(self)
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("Seleccione un diseño para iniciar.")

        root = QWidget(self)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        layout.addWidget(self._project_bar())
        self._content = QStackedWidget()
        placeholder = QLabel("Seleccione un diseño Icestudio (.ice) y pulse Ejecutar.")
        placeholder.setStyleSheet("color:#94a3b8; font-size:16px; padding:32px;")
        placeholder.setWordWrap(True)
        self._content.addWidget(placeholder)
        layout.addWidget(self._content, 1)
        self.setCentralWidget(root)

    def _project_bar(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("panel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.addWidget(QLabel("Proyecto Icestudio"))
        row = QHBoxLayout()
        self._path = QLineEdit()
        self._path.setReadOnly(True)
        self._path.setPlaceholderText("Seleccione un archivo .ice")
        browse = QPushButton("Buscar…")
        browse.clicked.connect(self._browse)
        self._recent = QComboBox()
        self._recent.setMinimumWidth(200)
        self._recent.addItem("Recientes", None)
        self._recent.currentIndexChanged.connect(self._choose_recent)
        self._refresh_recent()
        self._execute_button = QPushButton("▶ Ejecutar")
        self._execute_button.clicked.connect(self._request_project)
        self._stop_button = QPushButton("■ Detener")
        self._stop_button.setEnabled(False)
        self._stop_button.clicked.connect(self._request_stop)
        row.addWidget(self._path, 1)
        row.addWidget(browse)
        row.addWidget(self._recent)
        row.addWidget(self._execute_button)
        row.addWidget(self._stop_button)
        layout.addLayout(row)
        lab_row = QHBoxLayout()
        lab_row.addWidget(QLabel("Laboratorio"))
        self._labs = QComboBox()
        self._labs.currentIndexChanged.connect(self._choose_lab)
        self._refresh_labs()
        create_lab = QPushButton("Nuevo laboratorio…")
        create_lab.clicked.connect(self._create_lab)
        lab_row.addWidget(self._labs, 1)
        lab_row.addWidget(create_lab)
        layout.addLayout(lab_row)
        return frame

    def _refresh_labs(self) -> None:
        current = self._selected_lab
        self._labs.blockSignals(True)
        self._labs.clear()
        for descriptor in self._workspace.labs():
            self._labs.addItem(descriptor.name, descriptor.path)
        index = self._labs.findData(current)
        self._labs.setCurrentIndex(max(0, index))
        self._labs.blockSignals(False)

    def _choose_lab(self, index: int) -> None:
        path = self._labs.itemData(index)
        if path:
            self._selected_lab = Path(path)
            self._lab_explicitly_selected = True
            self.set_status(f"Laboratorio seleccionado: {self._labs.currentText()}")

    def _create_lab(self) -> None:
        name, accepted = QInputDialog.getText(self, "Nuevo laboratorio", "Nombre del laboratorio:")
        if not accepted:
            return
        descriptor = self._workspace.create(name)
        self._selected_lab = descriptor.path
        self._lab_explicitly_selected = True
        self._refresh_labs()
        self.set_status(f"Laboratorio creado: {descriptor.name}")

    def selected_lab(self) -> Path:
        return self._selected_lab

    def uses_default_lab(self) -> bool:
        return not self._lab_explicitly_selected

    def select_lab(self, path: Path) -> None:
        self._selected_lab = path
        self._refresh_labs()

    def _refresh_recent(self) -> None:
        selected = self.selected_project()
        self._recent.blockSignals(True)
        self._recent.clear()
        self._recent.addItem("Recientes", None)
        for path in self._recent_projects.paths():
            self._recent.addItem(path.name, path)
        self._recent.blockSignals(False)
        if selected:
            self.set_project_path(selected)

    def _browse(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar diseño Icestudio", "", "Diseños Icestudio (*.ice)"
        )
        if filename:
            self.set_project_path(Path(filename))

    def _choose_recent(self, index: int) -> None:
        path = self._recent.itemData(index)
        if path:
            self.set_project_path(Path(path))

    def _request_project(self) -> None:
        path = self.selected_project()
        if path is None:
            QMessageBox.information(self, "Proyecto Icestudio", "Seleccione un archivo .ice primero.")
            return
        self.project_requested.emit(path)

    def _request_stop(self) -> None:
        self.stop_requested.emit()

    def set_simulation_running(self, running: bool) -> None:
        self._stop_button.setEnabled(running)

    def selected_project(self) -> Path | None:
        text = self._path.text().strip()
        return Path(text) if text else None

    def set_project_path(self, path: str | Path) -> None:
        resolved = Path(path).expanduser().resolve()
        self._path.setText(str(resolved))
        self.set_status("Listo para ejecutar. Se reutilizará la caché si el diseño no cambió.")

    def set_status(self, message: str) -> None:
        self._status_bar.showMessage(message)

    def remember_project(self, path: Path) -> None:
        self._recent_projects.add(path)
        self._refresh_recent()

    def active_lab(self) -> QWidget | None:
        """Return the currently hosted laboratory widget."""
        return self._active_lab

    def set_lab(self, lab: QWidget) -> None:
        previous = self._active_lab
        self._active_lab = lab
        self._content.addWidget(lab)
        self._content.setCurrentWidget(lab)
        if previous is not None:
            self._content.removeWidget(previous)
            previous.close()
            previous.deleteLater()

    def closeEvent(self, event) -> None:
        if self._active_lab is not None:
            self._active_lab.close()
        super().closeEvent(event)
