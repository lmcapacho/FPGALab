"""Panel visual moderno para interactuar con una Alhambra II emulada."""

from __future__ import annotations

from PyQt6.QtCore import QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
                             QVBoxLayout, QWidget)

from .simulation import VerilatorSimulation
from .simulation_worker import SimulationWorker

_QSS = """
QWidget { background: #0f172a; color: #e2e8f0; font-family: Inter, Arial, sans-serif; }
QFrame#board { background: #1e3a2f; border: 2px solid #4ade80; border-radius: 22px; }
QFrame#panel { background: #172033; border: 1px solid #334155; border-radius: 14px; }
QPushButton#switch { background: #334155; border: 1px solid #64748b; border-radius: 10px; padding: 11px; font-weight: 700; }
QPushButton#switch:pressed { background: #22c55e; color: #052e16; }
QLabel#caption { color: #94a3b8; font-size: 11px; }
"""


class Led(QFrame):
    def __init__(self, color: str = "#22c55e"):
        super().__init__()
        self._color = color
        self.setFixedSize(24, 24)
        self.set_on(False)

    def set_on(self, enabled: bool) -> None:
        fill = self._color if enabled else "#334155"
        # Qt Style Sheets no implementa box-shadow; se evita el aviso del parser.
        border = self._color if enabled else "#64748b"
        self.setStyleSheet(f"background:{fill}; border:2px solid {border}; border-radius:12px;")


class SevenSegmentDisplay(QLabel):
    """Vista compacta: cada bit activo dibuja un segmento Unicode iluminado."""
    def __init__(self):
        super().__init__("— — — — — — —\n— — — — — — —")
        self.setStyleSheet("background:#020617; color:#334155; border-radius:10px; padding:10px; font: 22px monospace;")
        self.setAlignment(__import__("PyQt6.QtCore", fromlist=["Qt"]).Qt.AlignmentFlag.AlignCenter)

    def set_segments(self, bits: int) -> None:
        rows = []
        for offset in (0, 7):
            rows.append(" ".join("━" if bits & (1 << (offset + index)) else "·" for index in range(7)))
        self.setText("\n".join(rows))
        self.setStyleSheet("background:#020617; color:#f97316; border:1px solid #475569; border-radius:10px; padding:10px; font: 22px monospace;")


class FPGAVirtualLab(QWidget):
    """Ventana integrable. Sus señales se entregan al worker mediante Qt queued slots."""

    set_input_requested = pyqtSignal(str, int)
    shutdown_requested = pyqtSignal()

    def __init__(self, simulation: VerilatorSimulation, clock_hz: int = 12_000_000, ui_refresh_hz: int = 60, parent=None):
        super().__init__(parent)
        self.setWindowTitle("FPGALab · Laboratorio Virtual")
        self.setMinimumSize(800, 520)
        self.setStyleSheet(_QSS)
        self._bounce_timers: list[QTimer] = []
        self._board_name = simulation.profile.board_name
        self._build_ui()

        self._thread = QThread(self)
        self._worker = SimulationWorker(simulation, clock_hz, ui_refresh_hz)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.start)
        self.set_input_requested.connect(self._worker.set_input)
        self.shutdown_requested.connect(self._worker.shutdown)
        self._worker.state_changed.connect(self._paint_state)
        self._worker.failure.connect(self._show_failure)
        self._worker.stopped.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.start()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        board = QFrame(objectName="board")
        board_layout = QVBoxLayout(board)
        title = QLabel(f"{self._board_name.upper()} · FPGA VIRTUAL")
        title.setStyleSheet("font-size: 20px; font-weight: 800; color:#bbf7d0;")
        board_layout.addWidget(title)
        board_layout.addWidget(QLabel("Motor Verilator · reloj virtual en tiempo real", objectName="caption"))
        board_layout.addStretch()
        chip = QLabel("iCE40HX4K\nFPGA", alignment=__import__("PyQt6.QtCore", fromlist=["Qt"]).Qt.AlignmentFlag.AlignCenter)
        chip.setStyleSheet("background:#111827; border:2px solid #64748b; border-radius:16px; padding:42px; font-weight:800;")
        board_layout.addWidget(chip)
        board_layout.addStretch()
        root.addWidget(board, 2)

        controls = QVBoxLayout()
        switch_panel = QFrame(objectName="panel")
        switch_layout = QVBoxLayout(switch_panel)
        switch_layout.addWidget(QLabel("Pulsadores de placa"))
        for signal in ("SW1", "SW2"):
            button = QPushButton(signal, objectName="switch")
            button.pressed.connect(lambda pin=signal: self._bouncy_input(pin, 1))
            button.released.connect(lambda pin=signal: self._bouncy_input(pin, 0))
            switch_layout.addWidget(button)
        controls.addWidget(switch_panel)

        led_panel = QFrame(objectName="panel")
        led_layout = QGridLayout(led_panel)
        led_layout.addWidget(QLabel("LEDs de placa"), 0, 0, 1, 4)
        self._leds: list[Led] = []
        for index in range(8):
            led_layout.addWidget(QLabel(f"LED{index}", objectName="caption"), 1 + (index // 4) * 2, index % 4)
            led = Led()
            self._leds.append(led)
            led_layout.addWidget(led, 2 + (index // 4) * 2, index % 4)
        controls.addWidget(led_panel)

        display_panel = QFrame(objectName="panel")
        display_layout = QVBoxLayout(display_panel)
        display_layout.addWidget(QLabel("Display 7 segmentos · 2 dígitos"))
        self._display = SevenSegmentDisplay()
        display_layout.addWidget(self._display)
        self._gpio = QLabel("GPIO OUT: 00000000", objectName="caption")
        display_layout.addWidget(self._gpio)
        controls.addWidget(display_panel)
        root.addLayout(controls, 3)

    def _bouncy_input(self, name: str, final_value: int) -> None:
        """Tres cambios cortos hacen perceptible y configurable el rebote de botón."""
        values = [final_value, 1 - final_value, final_value]
        for index, value in enumerate(values):
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda v=value: self.set_input_requested.emit(name, v))
            timer.timeout.connect(timer.deleteLater)
            timer.start(index * 2)
            self._bounce_timers.append(timer)

    def _paint_state(self, leds: list, segments: int, gpio_out: int) -> None:
        for led, state in zip(self._leds, leds):
            led.set_on(bool(state))
        self._display.set_segments(segments)
        self._gpio.setText(f"GPIO OUT: {gpio_out:08b}")

    def _show_failure(self, error: str) -> None:
        self.setWindowTitle(f"FPGALab · simulación detenida: {error}")

    def closeEvent(self, event) -> None:
        # El timer se detiene dentro del QThread que lo creó.
        self.shutdown_requested.emit()
        if self._thread.wait(3000):
            event.accept()
        else:
            # Evita destruir el worker desde el hilo de la GUI.
            self._show_failure("esperando el cierre seguro de la simulación")
            event.ignore()
