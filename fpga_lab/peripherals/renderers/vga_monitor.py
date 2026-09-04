from __future__ import annotations

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor, QImage, QPainter

from ...i18n import t
from ...wiring import PeripheralInstance

PIXEL_WIDTH = 640
PIXEL_HEIGHT = 480
CHROME_LEFT = 8
CHROME_TOP = 24
CHROME_RIGHT = 8
CHROME_BOTTOM = 20


class VgaMonitorRenderer:
    def __init__(self) -> None:
        self._buf: bytearray | None = None
        self._image: QImage | None = None
        self._waiting = False
        self._off = False

    def size(self, peripheral: PeripheralInstance) -> tuple[int, int]:
        return (PIXEL_WIDTH + CHROME_LEFT + CHROME_RIGHT, PIXEL_HEIGHT + CHROME_TOP + CHROME_BOTTOM)

    def drop_images(self) -> None:
        self._image = None
        self._buf = None
        self._waiting = False
        self._off = True

    def apply_snapshot(self, snapshot) -> None:
        if snapshot is None:
            return
        pixels = snapshot.pixels
        if pixels is None:
            self._waiting = True
            self._off = False
            return
        if pixels == b"":
            self._image = None
            self._buf = None
            self._waiting = False
            self._off = True
            return
        self._off = False
        self._waiting = snapshot.seq == 0
        self._buf = bytearray(pixels)
        width = snapshot.width or PIXEL_WIDTH
        height = snapshot.height or PIXEL_HEIGHT
        self._image = QImage(self._buf, width, height, width * 4, QImage.Format.Format_ARGB32)

    def paint(self, painter: QPainter, rect, peripheral: PeripheralInstance, state) -> None:
        snapshot = state.get("snapshot")
        if snapshot is not None:
            self.apply_snapshot(snapshot)
        screen = QRect(
            int(rect.left()) + CHROME_LEFT,
            int(rect.top()) + CHROME_TOP,
            PIXEL_WIDTH,
            PIXEL_HEIGHT,
        )
        painter.fillRect(screen, QColor("#020617"))
        if self._image is not None and not self._image.isNull():
            painter.drawImage(screen.topLeft(), self._image)
        overlay = self._overlay_text(state, snapshot)
        if overlay:
            painter.setPen(QColor("#fbbf24"))
            painter.drawText(screen.adjusted(6, 6, -6, -6), Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft, overlay)
        painter.setPen(QColor("#64748b"))
        painter.drawText(
            QRect(int(rect.left()) + CHROME_LEFT, int(rect.bottom()) - CHROME_BOTTOM + 2, PIXEL_WIDTH, CHROME_BOTTOM - 4),
            Qt.AlignmentFlag.AlignLeft,
            t("Sink is 640×480; non-standard active widths look shifted."),
        )

    def _overlay_text(self, state, snapshot) -> str:
        if snapshot is not None:
            if snapshot.bind_errors:
                return "\n".join(snapshot.bind_errors)
            if snapshot.missing_required:
                missing = ", ".join(snapshot.missing_required)
                return t("Connect {terminals}", terminals=missing)
            if snapshot.stats and snapshot.stats.last_h_total and abs(int(snapshot.stats.last_h_total) - 800) > 2:
                return t("Unexpected H total {n} (expected 800). Check timings.", n=snapshot.stats.last_h_total)
        if self._off:
            return t("VGA capture off")
        if self._waiting:
            return t("Waiting for VSYNC…")
        return ""

    def mouse_press(self, peripheral, pos, input_changed) -> None:
        return

    def mouse_release(self, peripheral, pos, input_changed) -> None:
        return
