"""Opt-in SDK setup with background networking and cooperative cancellation."""

from __future__ import annotations

import platform
import sys
from threading import Event

from PyQt6.QtCore import QThread, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QProgressBar, QPushButton, QVBoxLayout,
)
from PyQt6.QtGui import QTextOption

from .i18n import t
from .private_toolchain import user_toolchains_root
from .sdk_install import SDKInstallCancelled, install_sdk, read_catalog
from .theme import Metrics, style_button


def sdk_download_supported() -> bool:
    return sys.platform == "linux" and platform.machine().lower() in ("x86_64", "amd64")


class ToolchainReportDialog(QDialog):
    """Resizable, selectable diagnostics with scrolling instead of a clipped message box."""

    def __init__(self, ready, message, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("Simulation toolchain"))
        self.setMinimumSize(500, 240)
        self.resize(680, 360)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*([Metrics.SPACE_LG] * 4))
        layout.setSpacing(Metrics.SPACE_LG)
        summary = QLabel(t("Simulation toolchain is ready.") if ready else t("Simulation toolchain is not ready."))
        summary.setObjectName("infoText" if ready else "warningText")
        summary.setWordWrap(True)
        layout.addWidget(summary)
        self.details = QPlainTextEdit()
        self.details.setAccessibleName(t("Toolchain details"))
        self.details.setReadOnly(True)
        self.details.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.details.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.details.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.details.setPlainText(message)
        layout.addWidget(self.details, 1)
        buttons = QHBoxLayout()
        buttons.addStretch()
        close = QPushButton(t("Close"))
        close.setAutoDefault(False)
        style_button(close, "primary" if ready or not sdk_download_supported() else "secondary")
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        primary = close
        if sdk_download_supported():
            download = QPushButton(t("Download SDK…"))
            download.setAutoDefault(False)
            style_button(download, "secondary" if ready else "primary")
            download.clicked.connect(self.accept)
            buttons.addWidget(download)
            if not ready:
                primary = download
        layout.addLayout(buttons)
        primary.setDefault(True)
        primary.setFocus(Qt.FocusReason.OtherFocusReason)


class SDKTask(QThread):
    """No widgets or simulation model access; emit plain data to the GUI."""

    result = pyqtSignal(object)
    progress = pyqtSignal(int, int)
    phase = pyqtSignal(str)

    def __init__(self, url, allow_local_http, entry=None, parent=None):
        super().__init__(parent)
        self._url = url
        self._local = allow_local_http
        self._entry = entry
        self._cancel = Event()

    def cancel(self):
        self._cancel.set()

    def run(self):
        try:
            if self._entry is None:
                value = read_catalog(self._url, allow_local_http=self._local)
                if self._cancel.is_set():
                    raise SDKInstallCancelled()
            else:
                value = install_sdk(
                    self._url, self._entry["id"], allow_local_http=self._local,
                    expected_entry=self._entry, cancel_requested=self._cancel.is_set,
                    progress=self.progress.emit, phase=self.phase.emit,
                )
            outcome = ("ok", value)
        except SDKInstallCancelled:
            outcome = ("cancelled", None)
        except Exception as error:
            outcome = ("error", str(error))
        self.result.emit(outcome)


class SDKInstallDialog(QDialog):
    """Catalog preview and explicit install consent; no automatic startup fetch."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("Download simulation SDK"))
        self.setMinimumWidth(580)
        self._worker = None
        self._outcome = None
        self._installing = False
        self._catalog_url = ""
        self._catalog_local = False
        self._close_when_stopped = False
        self.installed_sdk = None
        QApplication.instance().aboutToQuit.connect(self._finish_before_quit)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*([Metrics.SPACE_LG] * 4))
        layout.setSpacing(Metrics.SPACE_LG)
        description = QLabel(t(
            "Experimental: Ubuntu 24.04 x86-64 SDK. Use only a trusted catalog; "
            "the SDK contains executable build tools. No public catalog is configured yet."
        ))
        description.setWordWrap(True)
        layout.addWidget(description)
        layout.addWidget(QLabel(t("Catalog URL")))
        row = QHBoxLayout()
        self._url = QLineEdit()
        self._url.setPlaceholderText("https://…/catalog.json")
        self._url.setAccessibleName(t("Catalog URL"))
        self._load = QPushButton(t("Load catalog"))
        style_button(self._load)
        self._load.clicked.connect(self._load_catalog)
        row.addWidget(self._url, 1)
        row.addWidget(self._load)
        layout.addLayout(row)
        self._local = QCheckBox(t("Allow HTTP for trusted local/VM tests"))
        self._local.setToolTip(t("Only loopback and private IPv4 addresses are allowed. HTTP is not encrypted."))
        layout.addWidget(self._local)
        self._sdks = QComboBox()
        self._sdks.setAccessibleName(t("Available SDKs"))
        self._sdks.currentIndexChanged.connect(self._update_selection)
        layout.addWidget(self._sdks)
        self._details = QLabel()
        self._details.setWordWrap(True)
        self._details.setTextFormat(Qt.TextFormat.PlainText)
        self._details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self._details)
        location = QLabel(t("Installation folder: {path}", path=user_toolchains_root()))
        location.setWordWrap(True)
        location.setTextFormat(Qt.TextFormat.PlainText)
        location.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(location)
        priority = QLabel(t("Explicit tool settings and bundled SDKs keep priority over downloaded SDKs."))
        priority.setWordWrap(True)
        layout.addWidget(priority)
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        layout.addWidget(self._progress)
        self._status = QLabel(t("Load a trusted catalog to choose an SDK."))
        self._status.setWordWrap(True)
        self._status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self._status)
        buttons = QHBoxLayout()
        buttons.addStretch()
        self._close = QPushButton(t("Close"))
        style_button(self._close)
        self._close.clicked.connect(self.reject)
        self._install = QPushButton(t("Download and install"))
        style_button(self._install, "primary")
        self._install.clicked.connect(self._start_install)
        buttons.addWidget(self._close)
        buttons.addWidget(self._install)
        layout.addLayout(buttons)
        self._url.textChanged.connect(self._invalidate_catalog)
        self._local.toggled.connect(self._invalidate_catalog)
        self._set_busy(False)
        if not sdk_download_supported():
            self._load.setEnabled(False)
            self._status.setText(t("SDK downloads are currently supported only on Linux x86-64."))

    def _invalidate_catalog(self):
        self._sdks.clear()
        self._details.clear()
        self._install.setEnabled(False)

    def is_busy(self):
        return self._worker is not None

    def _finish_before_quit(self):
        # Only final application teardown waits. Ordinary Cancel/close stays asynchronous.
        # Never let Qt destroy a running QThread, including during an explicit app.quit().
        if self._worker is not None:
            self._worker.cancel()
            self._worker.wait()

    def _update_selection(self):
        entry = self._sdks.currentData()
        self._install.setEnabled(bool(entry) and self._worker is None)
        self._details.setText(t("Download: {size:.1f} MiB\nSHA-256: {digest}",
                                size=entry["size"] / 1024**2, digest=entry["sha256"]) if entry else "")

    def _set_busy(self, busy):
        for widget in (self._url, self._local, self._sdks, self._load):
            widget.setEnabled(not busy)
        self._load.setEnabled(not busy and sdk_download_supported())
        self._install.setEnabled(not busy and self._sdks.currentData() is not None)
        self._close.setText(t("Cancel") if busy else t("Close"))
        self._close.setEnabled(True)

    def _load_catalog(self):
        if self._worker is not None:
            return
        self._invalidate_catalog()
        self._catalog_url = self._url.text().strip()
        self._catalog_local = self._local.isChecked()
        self._installing = False
        self._status.setText(t("Loading SDK catalog…"))
        self._start_task(SDKTask(self._catalog_url, self._catalog_local, parent=self))

    def _start_install(self):
        entry = self._sdks.currentData()
        if self._worker is not None or entry is None:
            return
        self._installing = True
        self._status.setText(t("Preparing SDK download…"))
        self._start_task(SDKTask(self._catalog_url, self._catalog_local, entry, self))

    def _start_task(self, worker):
        self._worker = worker
        self._outcome = None
        self._progress.setRange(0, 0)
        self._set_busy(True)
        worker.result.connect(self._receive_result)
        worker.progress.connect(self._download_progress)
        worker.phase.connect(self._phase_changed)
        worker.finished.connect(self._task_finished)
        worker.start()

    def _receive_result(self, outcome):
        self._outcome = outcome

    def _download_progress(self, current, total):
        if self._close_when_stopped:
            return
        self._progress.setRange(0, 100)
        self._progress.setValue(current * 100 // total)
        self._status.setText(t("Downloading SDK: {current:.1f} / {total:.1f} MiB",
                               current=current / 1024**2, total=total / 1024**2))

    def _phase_changed(self, phase):
        if self._close_when_stopped:
            return
        messages = {
            "catalog": t("Checking SDK catalog…"),
            "download": t("Downloading SDK…"),
            "extract": t("Extracting SDK…"),
            "validate": t("Validating SDK…"),
            "publish": t("Finishing SDK installation…"),
        }
        self._progress.setRange(0, 0)
        self._status.setText(messages.get(phase, phase))

    def _task_finished(self):
        worker = self._worker
        self._worker = None
        worker.deleteLater()
        self._set_busy(False)
        self._progress.setRange(0, 100)
        status, value = self._outcome or ("error", t("The SDK task ended without a result."))
        if status == "ok" and self._installing:
            self.installed_sdk = value
            self._status.setText(t("SDK installed: {path}", path=value.root))
            self.accept()
            return
        if self._close_when_stopped:
            super().reject()
            return
        if status == "ok":
            for entry in value:
                if entry["platform"] == "linux-x86_64":
                    self._sdks.addItem(entry["id"], entry)
            self._status.setText(t("Choose an SDK, then download and install it.") if self._sdks.count()
                                 else t("No SDK for this platform is available in the catalog."))
        elif status == "cancelled":
            self._status.setText(t("SDK installation cancelled."))
        else:
            self._status.setText(t("SDK setup failed: {error}", error=value))
        self._progress.setValue(0)

    def reject(self):
        if self._worker is not None:
            self._close_when_stopped = True
            self._worker.cancel()
            self._status.setText(t("Cancelling SDK setup; waiting for the current operation to stop…"))
            self._close.setEnabled(False)
            return
        super().reject()

    def closeEvent(self, event):
        if self._worker is not None:
            self.reject()
            event.ignore()
        else:
            super().closeEvent(event)
