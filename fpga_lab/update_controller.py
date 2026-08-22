"""Non-blocking GUI controller for GitHub Releases update checks."""

from __future__ import annotations

from PyQt6.QtCore import QThread, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QMessageBox

from .i18n import t
from .updater import check_for_updates


class UpdateCheckWorker(QThread):
    """Run the network request outside the Qt GUI thread."""

    completed = pyqtSignal(dict)

    def run(self) -> None:
        self.completed.emit(check_for_updates())


class UpdateController:
    """Check published versions and direct the user to the release page."""

    def __init__(self, parent) -> None:
        self._parent = parent
        self._worker: UpdateCheckWorker | None = None
        self._manual_check = False

    def check_on_startup(self) -> None:
        """Perform one silent check after the application window is available."""
        self._start(manual=False)

    def check_manually(self) -> None:
        """Perform a visible update check requested by the user."""
        self._start(manual=True)

    def _start(self, *, manual: bool) -> None:
        if self._worker is not None:
            if manual:
                self._parent.set_status(t("An update check is already running.", "Ya hay una comprobación de actualización en curso."))
            return
        self._manual_check = manual
        self._worker = UpdateCheckWorker(self._parent)
        self._worker.completed.connect(self._finish)
        self._worker.finished.connect(self._clear_worker)
        self._worker.start()
        if manual:
            self._parent.set_status(t("Checking for updates…", "Buscando actualizaciones…"))

    def _clear_worker(self) -> None:
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.deleteLater()

    def _finish(self, result: dict) -> None:
        manual = self._manual_check
        if not result.get("ok"):
            if manual:
                QMessageBox.warning(
                    self._parent,
                    t("Update check failed", "No se pudo buscar actualizaciones"),
                    t("Could not check for updates: {error}", "No se pudo buscar actualizaciones: {error}", error=result.get("error", "unknown error")),
                )
            return
        if not result.get("update_available"):
            if manual:
                message = t(
                    "FPGALab is up to date ({version}).",
                    "FPGALab está actualizado ({version}).",
                    version=result["current_version"],
                )
                self._parent.set_status(message)
                QMessageBox.information(self._parent, t("No update available", "No hay actualización disponible"), message)
            return
        answer = QMessageBox.question(
            self._parent,
            t("Update available", "Actualización disponible"),
            t(
                "FPGALab {latest} is available (installed: {current}).\n\nOpen the release page?",
                "FPGALab {latest} está disponible (instalado: {current}).\n\n¿Abrir la página de la versión?",
                latest=result["latest_version"],
                current=result["current_version"],
            ),
        )
        if answer == QMessageBox.StandardButton.Yes:
            QDesktopServices.openUrl(QUrl(str(result["release_url"])))
