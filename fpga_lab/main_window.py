"""Main application shell with an integrated Icestudio project bar."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressDialog,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from .i18n import language_manager, t
from .lab_workspace import LabWorkspace
from .recent_projects import RecentProjects


class LabNameDialog(QDialog):
    """Purpose-built Lab naming dialog with predictable sizing on every platform."""

    def __init__(self, title: str, action: str, initial_name: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(360)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(t("Lab Name:")))
        self.name_field = QLineEdit()
        self.name_field.setText(initial_name)
        self.name_field.setPlaceholderText(t("New Lab"))
        layout.addWidget(self.name_field)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(action)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(t("Cancel"))
        buttons.accepted.connect(self._accept_if_named)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.name_field.setFocus()
        self.name_field.selectAll()

    def _accept_if_named(self) -> None:
        if self.name_field.text().strip():
            self.accept()


class LabManagerDialog(QDialog):
    """Search, select, create, and delete reusable labs from one compact view."""

    def __init__(self, workspace: LabWorkspace, selected_lab: Path, parent=None):
        super().__init__(parent)
        self._workspace = workspace
        self._selected_lab = selected_lab.resolve()
        self.setWindowTitle(t("Laboratories"))
        self.setMinimumSize(460, 360)
        layout = QVBoxLayout(self)
        self._search = QLineEdit()
        self._search.setPlaceholderText(t("Search labs…"))
        self._search.textChanged.connect(self._refresh)
        layout.addWidget(self._search)
        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(lambda _: self.accept())
        self._list.itemSelectionChanged.connect(self._update_actions)
        management_actions = QHBoxLayout()
        self._new_button = QPushButton(t("New Lab"))
        self._new_button.clicked.connect(self._create_lab)
        self._duplicate_button = QPushButton(t("Duplicate"))
        self._duplicate_button.clicked.connect(self._duplicate_lab)
        self._rename_button = QPushButton(t("Rename"))
        self._rename_button.clicked.connect(self._rename_lab)
        self._delete_button = QPushButton(t("Delete"))
        self._delete_button.clicked.connect(self._delete_lab)
        management_actions.addWidget(self._new_button)
        management_actions.addWidget(self._duplicate_button)
        management_actions.addWidget(self._rename_button)
        management_actions.addWidget(self._delete_button)
        management_actions.addStretch(1)
        layout.addLayout(management_actions)
        layout.addWidget(self._list, 1)
        selection_actions = QHBoxLayout()
        selection_actions.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Open)
        buttons.button(QDialogButtonBox.StandardButton.Open).setText(t("Open"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(t("Cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        selection_actions.addWidget(buttons)
        layout.addLayout(selection_actions)
        self._refresh()

    def selected_lab(self) -> Path | None:
        item = self._list.currentItem()
        return Path(item.data(Qt.ItemDataRole.UserRole)) if item is not None else None

    def _refresh(self) -> None:
        current = self.selected_lab() or self._selected_lab
        filter_text = self._search.text().strip().casefold()
        self._list.blockSignals(True)
        self._list.clear()
        for descriptor in self._workspace.labs():
            if filter_text and filter_text not in descriptor.name.casefold():
                continue
            name = t("My First Lab") if descriptor.path.name == "my-first-lab.lab.json" else descriptor.name
            item = QListWidgetItem(LabWorkspace.base_name(name))
            item.setData(Qt.ItemDataRole.UserRole, descriptor.path)
            item.setToolTip(name)
            self._list.addItem(item)
            if descriptor.path.resolve() == current.resolve():
                self._list.setCurrentItem(item)
        if self._list.currentItem() is None and self._list.count():
            self._list.setCurrentRow(0)
        self._list.blockSignals(False)
        self._update_actions()

    def _update_actions(self) -> None:
        selected = self.selected_lab()
        is_user_lab = selected is not None and selected.name != "my-first-lab.lab.json"
        self._duplicate_button.setEnabled(selected is not None)
        self._rename_button.setEnabled(is_user_lab)
        self._delete_button.setEnabled(is_user_lab)

    def _create_lab(self) -> None:
        dialog = LabNameDialog(t("New Lab"), t("Create"), parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        descriptor = self._workspace.create(dialog.name_field.text())
        self._selected_lab = descriptor.path.resolve()
        self._refresh()

    def _duplicate_lab(self) -> None:
        selected = self.selected_lab()
        if selected is None:
            return
        descriptor = self._workspace.duplicate(selected)
        self._selected_lab = descriptor.path.resolve()
        self._refresh()

    def _rename_lab(self) -> None:
        selected = self.selected_lab()
        if selected is None:
            return
        current_name = next(
            descriptor.name for descriptor in self._workspace.labs()
            if descriptor.path.resolve() == selected.resolve()
        )
        dialog = LabNameDialog(
            t("Rename Lab"),
            t("Rename"),
            LabWorkspace.base_name(current_name),
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        descriptor = self._workspace.rename(selected, dialog.name_field.text())
        self._selected_lab = descriptor.path.resolve()
        self._refresh()

    def _delete_lab(self) -> None:
        selected = self.selected_lab()
        if selected is None:
            return
        answer = QMessageBox.question(
            self,
            t("Delete Lab"),
            t("Delete Lab {name}?", name=self._list.currentItem().text()),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        if self._workspace.delete(selected):
            self._selected_lab = self._workspace.last_selected().resolve()
            self._refresh()

class FPGALabMainWindow(QMainWindow):
    """Persistent shell that selects and hosts one active virtual laboratory."""

    project_requested = pyqtSignal(Path)
    lab_selected = pyqtSignal(Path)
    stop_requested = pyqtSignal()
    toolchain_requested = pyqtSignal()
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
        self._selected_lab = self._workspace.last_selected()
        self._active_lab: QWidget | None = None
        self._busy_dialog: QProgressDialog | None = None
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
        self._toolchain_button = QPushButton("🛠")
        self._toolchain_button.setFixedSize(34, 24)
        self._toolchain_button.clicked.connect(self.toolchain_requested.emit)
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
        self._status_bar.addPermanentWidget(self._toolchain_button)
        self._status_bar.addPermanentWidget(self._run_button)
        self._status_bar.addPermanentWidget(self._stop_button)
        language_manager.language_changed.connect(self._retranslate_ui)
        self._retranslate_ui()
        self._restore_last_project()

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
        self._lab_button = QPushButton()
        self._lab_button.setMinimumWidth(210)
        self._lab_button.clicked.connect(self._open_lab_manager)
        self._refresh_labs()
        self._language = QComboBox()
        for language in language_manager.languages:
            self._language.addItem(language.upper(), language)
        self._language.setCurrentIndex(self._language.findData(language_manager.language))
        self._language.currentIndexChanged.connect(self._choose_language)
        self._language.setFixedWidth(58)
        layout.addWidget(self._project_label)
        layout.addWidget(self._path, 3)
        layout.addWidget(self._browse_button)
        layout.addWidget(self._recent)
        layout.addSpacing(8)
        layout.addWidget(self._lab_button, 2)
        layout.addWidget(self._language)
        return frame

    def _retranslate_ui(self) -> None:
        self.setWindowTitle(t("FPGALab · Virtual FPGA Lab"))
        self._project_label.setText(t("Project"))
        self._path.setPlaceholderText(t("Select an .ice file"))
        self._browse_button.setText(t("Browse…"))
        self._browse_button.setToolTip(t("Browse for an Icestudio design"))
        self._lab_button.setToolTip(t("Select or manage labs"))
        self._language.setToolTip(t("Interface language"))
        self._update_button.setToolTip(t("Check for updates"))
        self._toolchain_button.setToolTip(t("Check simulation toolchain"))
        self._run_button.setToolTip(t("Run selected project"))
        self._stop_button.setToolTip(t("Stop simulation"))
        self._placeholder.setText(t("Select an Icestudio design (.ice) to start."))
        if not self._status_bar.currentMessage():
            self._status_bar.showMessage(t("Select a design to start."))
        self._refresh_recent()

    def _choose_language(self, index: int) -> None:
        language = self._language.itemData(index)
        if language:
            language_manager.set_language(language)

    def _refresh_labs(self) -> None:
        current = self._selected_lab.resolve()
        current_name = current.stem.removesuffix(".lab")
        for descriptor in self._workspace.labs():
            display_name = descriptor.name
            if descriptor.path.name == "my-first-lab.lab.json":
                display_name = t("My First Lab")
            if descriptor.path.resolve() == current:
                current_name = self._button_lab_name(display_name)
                break
        self._lab_button.setText(current_name)
        self._update_lab_tooltip()

    def _update_lab_tooltip(self) -> None:
        self._lab_button.setToolTip(f"{t('Select or manage labs')}\n{self._selected_lab}")

    @staticmethod
    def _button_lab_name(name: str) -> str:
        """Keep the active selector explicit without repeating an existing suffix."""
        return name if name.casefold().endswith(" lab") else f"{name} Lab"

    def _open_lab_manager(self) -> None:
        dialog = LabManagerDialog(self._workspace, self._selected_lab, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if path := dialog.selected_lab():
            self._set_selected_lab(path, notify=True)

    def _set_selected_lab(self, path: Path, notify: bool) -> None:
        self._selected_lab = path.resolve()
        self._workspace.remember_selected(self._selected_lab)
        self._refresh_labs()
        if notify:
            self.set_status(t("Selected lab: {name}", name=self._lab_button.text()))
            self.lab_selected.emit(self._selected_lab)

    def selected_lab(self) -> Path:
        return self._selected_lab

    def select_lab(self, path: Path) -> None:
        self._set_selected_lab(path, notify=False)

    def _refresh_recent(self) -> None:
        self._recent.blockSignals(True)
        self._recent.clear()
        self._recent.addItem(t("Recent projects"), None)
        for path in self._recent_projects.paths():
            self._recent.addItem(path.name, path)
        self._recent.blockSignals(False)

    def _restore_last_project(self) -> None:
        """Prefill the previous valid design; the user still explicitly runs it."""
        if path := self._recent_projects.last_path():
            self._path.setText(str(path))
            self.set_status(t("Last project restored. Ready to run."))

    def _browse(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, t("Select Icestudio design"), "", t("Icestudio designs (*.ice)")
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
            QMessageBox.information(self, t("Icestudio project"), t("Select an .ice file first."))
            return
        self.project_requested.emit(path)

    def _request_stop(self) -> None:
        self.stop_requested.emit()

    def set_simulation_running(self, running: bool) -> None:
        """Keep the run controls mutually exclusive and visually unambiguous."""
        self._run_button.setEnabled(not running)
        self._stop_button.setEnabled(running)

    def set_project_loading(self, loading: bool) -> None:
        """Disable run controls while a background build owns the selected project."""
        self._run_button.setEnabled(not loading)
        self._stop_button.setEnabled(False)

    def selected_project(self) -> Path | None:
        text = self._path.text().strip()
        return Path(text) if text else None

    def set_project_path(self, path: str | Path) -> None:
        resolved = Path(path).expanduser().resolve()
        self._path.setText(str(resolved))
        self._recent_projects.add(resolved)
        self._refresh_recent()
        self.set_status(t("Ready to run. The cache will be reused if the design is unchanged."))

    def set_status(self, message: str) -> None:
        self._status_bar.showMessage(message)

    def show_busy(self, message: str) -> None:
        """Show an explicit, non-cancellable operation notice over the lab."""
        self.set_status(message)
        if self._busy_dialog is None:
            self._busy_dialog = QProgressDialog(self)
            self._busy_dialog.setWindowTitle("FPGALab")
            self._busy_dialog.setCancelButton(None)
            self._busy_dialog.setRange(0, 0)
            self._busy_dialog.setWindowModality(Qt.WindowModality.WindowModal)
            self._busy_dialog.setMinimumDuration(0)
        self._busy_dialog.setLabelText(message)
        self._busy_dialog.show()

    def dismiss_busy(self) -> None:
        """Close the current operation notice without changing the status text."""
        if self._busy_dialog is not None:
            self._busy_dialog.close()

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
