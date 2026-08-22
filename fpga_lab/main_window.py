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

from .i18n import language_manager, t
from .lab_workspace import LabWorkspace
from .recent_projects import RecentProjects


class FPGALabMainWindow(QMainWindow):
    """Persistent shell that selects and hosts one active virtual laboratory."""

    project_requested = pyqtSignal(Path)
    stop_requested = pyqtSignal()
    update_requested = pyqtSignal()

    def __init__(self, workspace: LabWorkspace, parent=None):
        super().__init__(parent)
        self.setMinimumSize(1000, 680)
        self.setStyleSheet("""
            QMainWindow, QWidget { background:#0f172a; color:#e2e8f0; font-family:Inter,Arial,sans-serif; }
            QFrame#panel { background:#172033; border:1px solid #334155; border-radius:10px; }
            QStatusBar { background:#172033; color:#fbbf24; border-top:1px solid #334155; font-weight:600; }
            QPushButton#runButton { background:#166534; border:1px solid #22c55e; color:#f0fdf4; font-weight:700; border-radius:5px; }
            QPushButton#runButton:hover { background:#15803d; }
            QPushButton#stopButton { background:#991b1b; border:1px solid #f87171; color:#fef2f2; font-weight:700; border-radius:5px; }
            QPushButton#stopButton:hover { background:#b91c1c; }
            QPushButton#runButton:disabled, QPushButton#stopButton:disabled { background:#1e293b; border-color:#334155; color:#64748b; }
        """)
        self._recent_projects = RecentProjects()
        self._workspace = workspace
        self._selected_lab = self._workspace.ensure_default()
        self._active_lab: QWidget | None = None
        self._status_bar = QStatusBar(self)
        self.setStatusBar(self._status_bar)

        root = QWidget(self)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        layout.addWidget(self._project_bar())
        self._content = QStackedWidget()
        self._placeholder = QLabel()
        self._placeholder.setStyleSheet("color:#94a3b8; font-size:16px; padding:32px;")
        self._placeholder.setWordWrap(True)
        self._content.addWidget(self._placeholder)
        layout.addWidget(self._content, 1)
        self.setCentralWidget(root)

        self._update_button = QPushButton("↻")
        self._update_button.setFixedSize(34, 24)
        self._update_button.clicked.connect(self.update_requested.emit)
        self._run_button = QPushButton("▶")
        self._run_button.setObjectName("runButton")
        self._run_button.setFixedSize(34, 24)
        self._run_button.clicked.connect(self._request_project)
        self._stop_button = QPushButton("■")
        self._stop_button.setObjectName("stopButton")
        self._stop_button.setFixedSize(34, 24)
        self._stop_button.setEnabled(False)
        self._stop_button.clicked.connect(self._request_stop)
        self._status_bar.addPermanentWidget(self._update_button)
        self._status_bar.addPermanentWidget(self._run_button)
        self._status_bar.addPermanentWidget(self._stop_button)
        language_manager.language_changed.connect(self._retranslate_ui)
        self._retranslate_ui()

    def _project_bar(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("panel")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)
        self._project_label = QLabel()
        self._path = QLineEdit()
        self._path.setReadOnly(True)
        self._browse_button = QPushButton()
        self._browse_button.clicked.connect(self._browse)
        self._recent = QComboBox()
        self._recent.setMinimumWidth(155)
        self._recent.currentIndexChanged.connect(self._choose_recent)
        self._refresh_recent()
        self._lab_label = QLabel()
        self._labs = QComboBox()
        self._labs.setMinimumWidth(190)
        self._labs.currentIndexChanged.connect(self._choose_lab)
        self._refresh_labs()
        self._new_lab_button = QPushButton("＋")
        self._new_lab_button.setFixedWidth(30)
        self._new_lab_button.clicked.connect(self._create_lab)
        self._language = QComboBox()
        self._language.addItem("EN", "en")
        self._language.addItem("ES", "es")
        self._language.setCurrentIndex(self._language.findData(language_manager.language))
        self._language.currentIndexChanged.connect(self._choose_language)
        self._language.setFixedWidth(58)
        layout.addWidget(self._project_label)
        layout.addWidget(self._path, 3)
        layout.addWidget(self._browse_button)
        layout.addWidget(self._recent)
        layout.addSpacing(8)
        layout.addWidget(self._lab_label)
        layout.addWidget(self._labs, 2)
        layout.addWidget(self._new_lab_button)
        layout.addWidget(self._language)
        return frame

    def _retranslate_ui(self) -> None:
        self.setWindowTitle(t("FPGALab · Virtual FPGA Lab", "FPGALab · Laboratorio Virtual"))
        self._project_label.setText(t("Project", "Proyecto"))
        self._path.setPlaceholderText(t("Select an .ice file", "Seleccione un archivo .ice"))
        self._browse_button.setText(t("Browse…", "Buscar…"))
        self._browse_button.setToolTip(t("Browse for an Icestudio design", "Buscar un diseño de Icestudio"))
        self._lab_label.setText(t("Lab", "Laboratorio"))
        self._new_lab_button.setToolTip(t("Create a new lab", "Crear un laboratorio nuevo"))
        self._language.setToolTip(t("Interface language", "Idioma de la interfaz"))
        self._update_button.setToolTip(t("Check for updates", "Buscar actualizaciones"))
        self._run_button.setToolTip(t("Run selected project", "Ejecutar proyecto seleccionado"))
        self._stop_button.setToolTip(t("Stop simulation", "Detener simulación"))
        self._placeholder.setText(t("Select an Icestudio design (.ice) to start.", "Seleccione un diseño Icestudio (.ice) para iniciar."))
        if not self._status_bar.currentMessage():
            self._status_bar.showMessage(t("Select a design to start.", "Seleccione un diseño para iniciar."))
        self._refresh_recent()

    def _choose_language(self, index: int) -> None:
        language = self._language.itemData(index)
        if language:
            language_manager.set_language(language)

    def _refresh_labs(self) -> None:
        current = self._selected_lab
        self._labs.blockSignals(True)
        self._labs.clear()
        for descriptor in self._workspace.labs():
            display_name = descriptor.name
            if descriptor.path.name == "my-first-lab.lab.json":
                display_name = t("My first lab", "Mi primer laboratorio")
            self._labs.addItem(display_name, descriptor.path)
        index = self._labs.findData(current)
        self._labs.setCurrentIndex(max(0, index))
        self._labs.blockSignals(False)
        self._update_lab_tooltip()

    def _update_lab_tooltip(self) -> None:
        self._labs.setToolTip(str(self._selected_lab))

    def _choose_lab(self, index: int) -> None:
        path = self._labs.itemData(index)
        if path:
            self._selected_lab = Path(path)
            self._update_lab_tooltip()
            self.set_status(t("Selected lab: {name}", "Laboratorio seleccionado: {name}", name=self._labs.currentText()))

    def _create_lab(self) -> None:
        name, accepted = QInputDialog.getText(self, t("New lab", "Nuevo laboratorio"), t("Lab name:", "Nombre del laboratorio:"))
        if not accepted:
            return
        descriptor = self._workspace.create(name)
        self._selected_lab = descriptor.path
        self._refresh_labs()
        self.set_status(t("Lab created: {name}", "Laboratorio creado: {name}", name=descriptor.name))

    def selected_lab(self) -> Path:
        return self._selected_lab

    def select_lab(self, path: Path) -> None:
        self._selected_lab = path
        self._refresh_labs()

    def _refresh_recent(self) -> None:
        self._recent.blockSignals(True)
        self._recent.clear()
        self._recent.addItem(t("Recent projects", "Proyectos recientes"), None)
        for path in self._recent_projects.paths():
            self._recent.addItem(path.name, path)
        self._recent.blockSignals(False)

    def _browse(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, t("Select Icestudio design", "Seleccionar diseño Icestudio"), "", t("Icestudio designs (*.ice)", "Diseños Icestudio (*.ice)")
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
            QMessageBox.information(self, t("Icestudio project", "Proyecto Icestudio"), t("Select an .ice file first.", "Seleccione un archivo .ice primero."))
            return
        self.project_requested.emit(path)

    def _request_stop(self) -> None:
        self.stop_requested.emit()

    def set_simulation_running(self, running: bool) -> None:
        """Keep the run controls mutually exclusive and visually unambiguous."""
        self._run_button.setEnabled(not running)
        self._stop_button.setEnabled(running)

    def selected_project(self) -> Path | None:
        text = self._path.text().strip()
        return Path(text) if text else None

    def set_project_path(self, path: str | Path) -> None:
        resolved = Path(path).expanduser().resolve()
        self._path.setText(str(resolved))
        self._recent_projects.add(resolved)
        self._refresh_recent()
        self.set_status(t("Ready to run. The cache will be reused if the design is unchanged.", "Listo para ejecutar. Se reutilizará la caché si el diseño no cambió."))

    def set_status(self, message: str) -> None:
        self._status_bar.showMessage(message)

    def remember_project(self, path: Path) -> None:
        self.set_project_path(path)

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
