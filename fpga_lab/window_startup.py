"""Initial window mapping without racing the Wayland configure handshake."""

from PyQt6.QtCore import QEvent, QObject, QTimer
from PyQt6.QtWidgets import QApplication


class _MaximizeOnExposure(QObject):
    def __init__(self, window, handle):
        super().__init__(window)
        self._window = window
        self._handle = handle
        self._scheduled = False
        handle.installEventFilter(self)
        self.schedule_if_exposed()

    def schedule_if_exposed(self):
        if not self._scheduled and self._handle.isExposed():
            self._scheduled = True
            self._handle.removeEventFilter(self)
            QTimer.singleShot(0, self._maximize)

    def _maximize(self):
        if self._window.isVisible() and not self._window.isMinimized():
            self._window.showMaximized()
        self.deleteLater()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Expose:
            self.schedule_if_exposed()
        return False


def show_main_window(window, *, platform_name=None):
    platform_name = platform_name or QApplication.platformName()
    if not platform_name.startswith("wayland"):
        window.showMaximized()
        return
    # Map a normal surface first. Let Qt/compositor complete its first exposure
    # before requesting maximization, rather than repeating requests on a timer.
    window.show()
    handle = window.windowHandle()
    if handle is not None:
        _MaximizeOnExposure(window, handle)
