"""Main application shell with an integrated Icestudio project bar."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGridLayout,
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
from .theme import Metrics, style_button


def _style_lab_icon_button(button: QPushButton, icon_name: str) -> None:
    """Apply a compact bundled icon without coupling Lab management to the global theme."""
    icon_path = Path(__file__).resolve().parent / "assets" / "icons" / "ui" / f"{icon_name}.svg"
    button.setIcon(QIcon(str(icon_path)))
    button.setFixedSize(32, 28)


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
        style_button(buttons.button(QDialogButtonBox.StandardButton.Ok), "primary")
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

    active_lab_changed = pyqtSignal(Path)

    def __init__(self, workspace: LabWorkspace, selected_lab: Path, parent=None):
        super().__init__(parent)
        self._workspace = workspace
        self._selected_lab = selected_lab.resolve()
        self._active_lab_path = selected_lab.resolve()
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
        management_actions = QGridLayout()
        self._new_button = QPushButton(t("New Lab"))
        self._new_button.clicked.connect(self._create_lab)
        self._import_button = QPushButton()
        _style_lab_icon_button(self._import_button, "import")
        self._import_button.setToolTip(t("Import Lab from file"))
        self._import_button.clicked.connect(self._import_lab)
        self._duplicate_button = QPushButton()
        _style_lab_icon_button(self._duplicate_button, "duplicate")
        self._duplicate_button.setToolTip(t("Duplicate selected Lab"))
        self._duplicate_button.clicked.connect(self._duplicate_lab)
        self._rename_button = QPushButton()
        _style_lab_icon_button(self._rename_button, "rename")
        self._rename_button.setToolTip(t("Rename selected Lab"))
        self._rename_button.clicked.connect(self._rename_lab)
        self._export_button = QPushButton()
        _style_lab_icon_button(self._export_button, "export")
        self._export_button.setToolTip(t("Export selected Lab"))
        self._export_button.clicked.connect(self._export_lab)
        self._delete_button = QPushButton()
        _style_lab_icon_button(self._delete_button, "delete")
        self._delete_button.setToolTip(t("Delete selected Lab"))
        self._delete_button.clicked.connect(self._delete_lab)
        management_actions.addWidget(self._new_button, 0, 0)
        management_actions.setColumnStretch(1, 1)
        management_actions.addWidget(self._import_button, 0, 2)
        management_actions.addWidget(self._duplicate_button, 0, 3)
        management_actions.addWidget(self._rename_button, 0, 4)
        management_actions.addWidget(self._export_button, 0, 5)
        management_actions.addWidget(self._delete_button, 0, 6)
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
            name = t("My First Lab") if LabWorkspace.is_starter_lab(descriptor.path) else descriptor.name
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
        is_user_lab = selected is not None and not LabWorkspace.is_starter_lab(selected)
        self._duplicate_button.setEnabled(selected is not None)
        self._export_button.setEnabled(selected is not None)
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

    def _import_lab(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            t("Import Lab"),
            "",
            t("FPGALab Labs (*.lab *.lab.json *.json)"),
        )
        if not filename:
            return
        try:
            descriptor = self._workspace.import_lab(filename)
        except ValueError as error:
            QMessageBox.warning(self, t("Import Lab"), t(str(error)))
            return
        self._selected_lab = descriptor.path.resolve()
        self._refresh()
        QMessageBox.information(
            self,
            t("Import Lab"),
            t("Lab imported: {name}", name=LabWorkspace.base_name(descriptor.name)),
        )

    def _export_lab(self) -> None:
        selected = self.selected_lab()
        if selected is None:
            return
        current_name = self._list.currentItem().text()
        suggested = f"{LabWorkspace._lab_stem(current_name)}.lab"
        filename, _ = QFileDialog.getSaveFileName(
            self,
            t("Export Lab"),
            suggested,
            t("FPGALab Labs (*.lab)"),
        )
        if not filename:
            return
        try:
            exported = self._workspace.export_lab(selected, filename)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, t("Export Lab"), str(error))
            return
        QMessageBox.information(
            self,
            t("Export Lab"),
            t("Lab exported to:\n{path}", path=exported),
        )

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
        if selected.resolve() == self._active_lab_path:
            self._active_lab_path = descriptor.path.resolve()
            self.active_lab_changed.emit(self._active_lab_path)
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
        deleting_active = selected.resolve() == self._active_lab_path
        if self._workspace.delete(selected):
            self._selected_lab = self._workspace.ensure_default().resolve() if deleting_active else self._workspace.last_selected().resolve()
            if deleting_active:
                self._active_lab_path = self._selected_lab
                self.active_lab_changed.emit(self._active_lab_path)
            self._refresh()

class FPGALabMainWindow(QMainWindow):
    """Persistent shell that selects and hosts one active virtual laboratory."""

    project_requested = pyqtSignal(Path)
    lab_selected = pyqtSignal(Path)
    stop_requested = pyqtSignal()
    toolchain_requested = pyqtSignal()
    simulation_settings_requested = pyqtSignal()
    update_requested = pyqtSignal()

    def __init__(self, workspace: LabWorkspace, parent=None):
        super().__init__(parent)
        self.setMinimumSize(1000, 680)
        self._recent_projects = RecentProjects()
        self._workspace = workspace
        self._selected_lab = self._workspace.last_selected()
        self._active_lab: QWidget | None = None
        self._busy_dialog: QProgressDialog | None = None
        self._status_bar = QStatusBar(self)
        self.setStatusBar(self._status_bar)
        self._requested_clock_hz: float | None = None
        self._achieved_clock_hz: float | None = None

        root = QWidget(self)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(Metrics.SPACE_MD, Metrics.SPACE_SM, Metrics.SPACE_MD, Metrics.SPACE_SM)
        layout.setSpacing(Metrics.SPACE_SM)
        layout.addWidget(self._project_bar())
        self._content = QStackedWidget()
        self._placeholder = QLabel()
        self._placeholder.setObjectName("emptyState")
        self._placeholder.setWordWrap(True)
        self._content.addWidget(self._placeholder)
        layout.addWidget(self._content, 1)
        self.setCentralWidget(root)

        self._update_button = QPushButton()
        style_button(self._update_button, "icon", "refresh")
        self._update_button.clicked.connect(self.update_requested.emit)
        self._toolchain_button = QPushButton()
        style_button(self._toolchain_button, "icon", "tools")
        self._toolchain_button.clicked.connect(self.toolchain_requested.emit)
        self._simulation_settings_button = QPushButton()
        style_button(self._simulation_settings_button, "icon", "settings")
        self._simulation_settings_button.clicked.connect(self.simulation_settings_requested.emit)
        self._run_button = QPushButton()
        style_button(self._run_button, "success", "play")
        self._run_button.setFixedSize(Metrics.ICON_BUTTON_WIDTH, Metrics.CONTROL_HEIGHT)
        self._run_button.clicked.connect(self._request_project)
        self._stop_button = QPushButton()
        style_button(self._stop_button, "danger", "stop")
        self._stop_button.setFixedSize(Metrics.ICON_BUTTON_WIDTH, Metrics.CONTROL_HEIGHT)
        self._stop_button.setEnabled(False)
        self._stop_button.clicked.connect(self._request_stop)
        self._clock_status = QLabel()
        self._clock_status.setObjectName("clockStatus")
        self._status_bar.addPermanentWidget(self._clock_status)
        self._status_bar.addPermanentWidget(self._update_button)
        self._status_bar.addPermanentWidget(self._toolchain_button)
        self._status_bar.addPermanentWidget(self._simulation_settings_button)
        self._status_bar.addPermanentWidget(self._run_button)
        self._status_bar.addPermanentWidget(self._stop_button)
        language_manager.language_changed.connect(self._retranslate_ui)
        self._retranslate_ui()
        self._restore_last_project()

    def _project_bar(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("panel")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(Metrics.SPACE_LG, Metrics.SPACE_SM, Metrics.SPACE_LG, Metrics.SPACE_SM)
        layout.setSpacing(Metrics.SPACE_SM)
        self._project_label = QLabel()
        self._path = QLineEdit()
        self._path.setReadOnly(True)
        self._browse_button = QPushButton()
        style_button(self._browse_button, "selector")
        self._browse_button.clicked.connect(self._browse)
        self._recent = QComboBox()
        self._recent.setMinimumWidth(155)
        self._recent.currentIndexChanged.connect(self._choose_recent)
        self._refresh_recent()
        self._lab_button = QPushButton()
        style_button(self._lab_button, "selector")
        self._lab_button.setMinimumWidth(210)
        self._lab_button.clicked.connect(self._open_lab_manager)
        self._refresh_labs()
        self._language = QComboBox()
        self._language.setObjectName("languageSelector")
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
        self._simulation_settings_button.setToolTip(t("Simulation settings"))
        self._run_button.setToolTip(t("Run selected project"))
        self._stop_button.setToolTip(t("Stop simulation"))
        self._refresh_clock_status()
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
            if LabWorkspace.is_starter_lab(descriptor.path):
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
        dialog.active_lab_changed.connect(lambda path: self._set_selected_lab(path, notify=True))
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
        for path in self._recent_projects.paths():
            self._recent.addItem(path.name, path)
        self._recent.setPlaceholderText(t("Recent projects"))
        self._recent.setCurrentIndex(-1)
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
        self._recent.setCurrentIndex(-1)

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
        self._set_configuration_controls_enabled(not running)

    def set_project_loading(self, loading: bool) -> None:
        """Freeze model-changing controls while a background build owns the project."""
        self._run_button.setEnabled(not loading)
        self._stop_button.setEnabled(False)
        self._set_configuration_controls_enabled(not loading)

    def _set_configuration_controls_enabled(self, enabled: bool) -> None:
        """Block actions that would replace or reconfigure the active model."""
        self._browse_button.setEnabled(enabled)
        self._recent.setEnabled(enabled)
        self._lab_button.setEnabled(enabled)
        self._simulation_settings_button.setEnabled(enabled)

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

    def set_clock_performance(
        self,
        requested_hz: float | None,
        achieved_hz: float | None = None,
    ) -> None:
        """Update the permanent virtual-clock indicator without hiding messages."""
        self._requested_clock_hz = requested_hz
        self._achieved_clock_hz = achieved_hz
        self._refresh_clock_status()

    def _refresh_clock_status(self) -> None:
        if self._requested_clock_hz is None:
            self._clock_status.setText(t("Combinational design"))
            return
        requested = _format_frequency(self._requested_clock_hz)
        actual = _format_frequency(self._achieved_clock_hz) if self._achieved_clock_hz is not None else "—"
        self._clock_status.setText(t(
            "Clock: {requested} · Actual: {actual}",
            requested=requested,
            actual=actual,
        ))

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


def _format_frequency(frequency_hz: float) -> str:
    """Format clock rates compactly while keeping useful precision."""
    if frequency_hz >= 1_000_000:
        return f"{frequency_hz / 1_000_000:.3f} MHz"
    if frequency_hz >= 1_000:
        return f"{frequency_hz / 1_000:.3f} kHz"
    return f"{frequency_hz:.0f} Hz"
