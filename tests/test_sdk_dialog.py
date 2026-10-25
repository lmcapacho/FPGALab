"""GUI SDK setup: thread boundary, consent, cancellation and error recovery."""

from threading import Event
from time import monotonic
from types import SimpleNamespace

from PyQt6.QtCore import QThread, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QPushButton

import fpga_lab.sdk_dialog as gui


_APP = QApplication.instance() or QApplication([])
_ENTRY = {"id": "test-sdk1", "platform": "linux-x86_64", "url": "https://example.test/sdk.tar.gz",
          "size": 1024, "sha256": "a" * 64}


def settle(dialog):
    deadline = monotonic() + 5
    while dialog.is_busy() and monotonic() < deadline:
        _APP.processEvents()
        QTest.qWait(5)
    assert not dialog.is_busy()
    _APP.processEvents()


def test_sdk_gui_load_and_install_run_off_gui_thread_and_pin_consent(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(gui, "sdk_download_supported", lambda: True)
    monkeypatch.setattr(gui, "user_toolchains_root", lambda: tmp_path / "toolchains")
    def catalog(url, **kwargs):
        assert QThread.currentThread() is not _APP.thread()
        calls.append(("catalog", url))
        return (_ENTRY,)
    def install(url, sdk_id, **kwargs):
        assert QThread.currentThread() is not _APP.thread()
        assert kwargs["expected_entry"] == _ENTRY
        assert not kwargs["cancel_requested"]()
        kwargs["phase"]("download")
        kwargs["progress"](1024, 1024)
        kwargs["phase"]("extract")
        calls.append(("install", sdk_id))
        return SimpleNamespace(root=tmp_path / "toolchains/test-sdk1")
    monkeypatch.setattr(gui, "read_catalog", catalog)
    monkeypatch.setattr(gui, "install_sdk", install)
    dialog = gui.SDKInstallDialog()
    try:
        assert calls == []  # Construction never contacts a catalog.
        assert not dialog._install.isEnabled()
        dialog._url.setText("https://example.test/catalog.json")
        dialog._load.click()
        assert dialog.is_busy() and not dialog._url.isEnabled()
        settle(dialog)
        assert dialog._sdks.currentData() == _ENTRY and dialog._install.isEnabled()
        dialog._install.click()
        settle(dialog)
        assert dialog.result() == dialog.DialogCode.Accepted
        assert dialog.installed_sdk.root == tmp_path / "toolchains/test-sdk1"
        assert calls == [("catalog", "https://example.test/catalog.json"), ("install", "test-sdk1")]
    finally:
        settle(dialog)
        dialog.close()
        dialog.deleteLater()


def test_toolchain_report_keeps_long_diagnostics_selectable_and_scrollable(monkeypatch):
    message = "Verilator was not found. Install Icestudio/Apio, configure a toolchain, or download an SDK.\n" * 50
    dialog = gui.ToolchainReportDialog(False, message)
    try:
        dialog.show()
        _APP.processEvents()
        assert dialog.details.toPlainText() == message
        assert dialog.details.isReadOnly()
        assert dialog.details.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByKeyboard
        assert dialog.details.verticalScrollBar().maximum() > 0
        assert dialog.details.height() > 100
        dialog.details.selectAll()
        assert dialog.details.textCursor().selectedText()
    finally:
        dialog.close()
        dialog.deleteLater()
    for ready, supported in ((True, True), (False, True), (False, False)):
        monkeypatch.setattr(gui, "sdk_download_supported", lambda: supported)
        for key in (Qt.Key.Key_Return, Qt.Key.Key_Escape):
            dialog = gui.ToolchainReportDialog(ready, message)
            try:
                dialog.show()
                _APP.processEvents()
                primary = dialog.focusWidget()
                assert isinstance(primary, QPushButton) and primary.isDefault()
                assert primary.property("role") == "primary"
                assert not dialog.details.hasFocus()
                assert len([button for button in dialog.findChildren(QPushButton) if button.isDefault()]) == 1
                QTest.keyClick(primary, key)
                accepted = key == Qt.Key.Key_Return and not ready and supported
                assert dialog.result() == (dialog.DialogCode.Accepted if accepted else dialog.DialogCode.Rejected)
                assert not dialog.isVisible()
            finally:
                dialog.close()
                dialog.deleteLater()


def test_sdk_gui_close_defers_thread_destruction_until_cancellation_finishes(monkeypatch):
    release, started = Event(), Event()
    monkeypatch.setattr(gui, "sdk_download_supported", lambda: True)
    def catalog(*args, **kwargs):
        started.set()
        assert release.wait(3)
        return (_ENTRY,)
    monkeypatch.setattr(gui, "read_catalog", catalog)
    dialog = gui.SDKInstallDialog()
    try:
        dialog.show()
        dialog._url.setText("https://example.test/catalog.json")
        dialog._load.click()
        assert started.wait(1)
        worker = dialog._worker
        assert dialog.close() is False
        assert dialog.is_busy() and dialog.isVisible() and worker.isRunning()
        assert not dialog._close.isEnabled()
        release.set()
        settle(dialog)
        assert not dialog.isVisible() and dialog.result() == dialog.DialogCode.Rejected
    finally:
        release.set()
        settle(dialog)
        dialog.close()
        dialog.deleteLater()


def test_sdk_gui_invalidates_changed_catalog_and_recovers_from_errors(monkeypatch):
    monkeypatch.setattr(gui, "sdk_download_supported", lambda: True)
    monkeypatch.setattr(gui, "read_catalog", lambda *args, **kwargs: (_ENTRY,))
    dialog = gui.SDKInstallDialog()
    try:
        dialog._url.setText("https://example.test/catalog.json")
        dialog._load.click()
        settle(dialog)
        assert dialog._install.isEnabled()
        dialog._local.setChecked(True)
        assert dialog._sdks.count() == 0 and not dialog._install.isEnabled()
        dialog._load.click()
        settle(dialog)
        def fail(*args, **kwargs):
            raise ValueError("synthetic integrity failure")
        monkeypatch.setattr(gui, "install_sdk", fail)
        dialog._install.click()
        settle(dialog)
        assert "synthetic integrity failure" in dialog._status.text()
        assert dialog.installed_sdk is None and dialog._load.isEnabled()
        assert dialog._install.isEnabled()  # Retry is possible without restarting the app.
        dialog._url.setText("https://other.test/catalog.json")
        assert dialog._sdks.count() == 0 and not dialog._install.isEnabled()
    finally:
        settle(dialog)
        dialog.close()
        dialog.deleteLater()
