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
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .recent_projects import RecentProjects


class FPGALabMainWindow(QMainWindow):
    """Persistent shell that selects and hosts one active virtual laboratory."""

    project_requested = pyqtSignal(Path)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("FPGALab · Laboratorio Virtual")
        self.setMinimumSize(1000, 680)
        self.setStyleSheet("""
            QMainWindow, QWidget { background:#0f172a; color:#e2e8f0; font-family:Inter,Arial,sans-serif; }
            QFrame#panel { background:#172033; border:1px solid #334155; border-radius:10px; }
            QLabel#caption { color:#94a3b8; font-size:11px; }
        """)
        self._recent_projects = RecentProjects()
        self._active_lab: QWidget | None = None

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
        run = QPushButton("▶ Iniciar simulación")
        run.clicked.connect(self._request_project)
        row.addWidget(self._path, 1)
        row.addWidget(browse)
        row.addWidget(self._recent)
        row.addWidget(run)
        layout.addLayout(row)
        self._status = QLabel("Seleccione un diseño para iniciar.")
        self._status.setObjectName("caption")
        layout.addWidget(self._status)
        return frame

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

    def selected_project(self) -> Path | None:
        text = self._path.text().strip()
        return Path(text) if text else None

    def set_project_path(self, path: str | Path) -> None:
        resolved = Path(path).expanduser().resolve()
        self._path.setText(str(resolved))
        self._status.setText("Listo para ejecutar. Se reutilizará la caché si el diseño no cambió.")

    def set_status(self, message: str) -> None:
        self._status.setText(message)

    def remember_project(self, path: Path) -> None:
        self._recent_projects.add(path)
        self._refresh_recent()

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
