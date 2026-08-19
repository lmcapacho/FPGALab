"""Modern visual panel for interacting with an emulated Alhambra II."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QMetaObject, QThread, QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMenuBar, QPushButton, QVBoxLayout, QWidget

from .board import BoardDefinition
from .board_editor import BoardLayoutEditor
from .peripherals_panel import PeripheralsPanel
from .board_layout import BoardLayout, bundled_layout
from .board_view import BoardView
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


class SevenSegmentDisplay(QLabel):
    """Compact view: each active bit draws an illuminated Unicode segment."""
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
    """Embeddable window. Signals reach the worker through queued Qt slots."""

    set_input_requested = pyqtSignal(str, int)
    shutdown_requested = pyqtSignal()
    play_requested = pyqtSignal()
    pause_requested = pyqtSignal()
    reset_requested = pyqtSignal()

    def __init__(
        self,
        simulation: VerilatorSimulation,
        clock_hz: int = 12_000_000,
        ui_refresh_hz: int = 60,
        observation_hz: int = 1_000_000,
        project_pcf: Path | None = None,
        lab_file: Path | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("FPGALab · Laboratorio Virtual")
        self.setMinimumSize(800, 520)
        self.setStyleSheet(_QSS)
        self._bounce_timers: list[QTimer] = []
        self._board_name = simulation.profile.board_name
        self._available_inputs = frozenset(simulation.profile.inputs)
        self._has_clock = simulation.profile.clock_name is not None
        self._input_widths = dict(simulation.profile.inputs)
        self._layout = BoardLayout.load(bundled_layout())
        self._project_pcf = project_pcf or Path("examples/main.pcf")
        self._lab_file = lab_file or Path("examples/lab.json")
        self._build_ui()

        self._thread = QThread(self)
        self._worker = SimulationWorker(simulation, clock_hz, ui_refresh_hz, observation_hz)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.start)
        self.set_input_requested.connect(self._worker.set_input)
        self.shutdown_requested.connect(self._worker.shutdown)
        self.play_requested.connect(self._worker.play)
        self.pause_requested.connect(self._worker.power_off)
        self.reset_requested.connect(self._worker.reset)
        self._worker.state_changed.connect(self._paint_state)
        self._worker.failure.connect(self._show_failure)
        self._worker.stopped.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.start()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        menu_bar = QMenuBar(self)
        board_menu = menu_bar.addMenu("Placa")
        edit_layout = board_menu.addAction("Editar layout…")
        edit_layout.triggered.connect(self._open_layout_editor)
        outer.addWidget(menu_bar)
        root = QHBoxLayout()
        outer.addLayout(root)
        board_panel = QFrame(objectName="board")
        board_panel.setMinimumWidth(380)
        board_layout = QVBoxLayout(board_panel)
        title = QLabel(f"{self._board_name.upper()} · FPGA VIRTUAL")
        title.setStyleSheet("font-size: 20px; font-weight: 800; color:#bbf7d0;")
        board_layout.addWidget(title)
        board_layout.addWidget(QLabel("SVG + layout de placa · controles interactivos", objectName="caption"))
        self._board_view = BoardView(self._layout, self._bouncy_input)
        board_layout.addWidget(self._board_view, 1)
        root.addWidget(board_panel, 3)

        controls = QVBoxLayout()
        info_panel = QFrame(objectName="panel")
        info_layout = QVBoxLayout(info_panel)
        info_layout.addWidget(QLabel("Controles integrados"))
        info_layout.addWidget(QLabel("Presione SW1 o SW2 directamente sobre la placa.", objectName="caption"))
        initial_state = "Estado: diseño combinacional · evaluación reactiva" if self._has_clock is False else "Estado: detenido"
        self._run_state = QLabel(initial_state, objectName="caption")
        info_layout.addWidget(self._run_state)
        run_buttons = QHBoxLayout()
        play = QPushButton("▶ Ejecutar")
        play.clicked.connect(self._play)
        pause = QPushButton("■ Detener")
        pause.clicked.connect(self._pause)
        if self._has_clock is False:
            play.setEnabled(False)
            pause.setEnabled(False)
        run_buttons.addWidget(play); run_buttons.addWidget(pause)
        info_layout.addLayout(run_buttons)
        controls.addWidget(info_panel)
        gpio_panel = QFrame(objectName="panel")
        gpio_layout = QVBoxLayout(gpio_panel)
        self._peripherals = PeripheralsPanel(
            BoardDefinition.load(Path("boards/alhambra_ii.json")),
            self._project_pcf,
            self._lab_file,
            self._input_widths,
        )
        self._peripherals.input_changed.connect(self.set_input_requested)
        gpio_layout.addWidget(self._peripherals, 1)
        controls.addWidget(gpio_panel, 1)
        root.addLayout(controls, 2)

    def _play(self) -> None:
        self.play_requested.emit()
        self._board_view.set_led_brightness("PWR", 1.0)
        self._run_state.setText("Estado: ejecutando · edición bloqueada")
        self._peripherals.set_editable(False)

    def _pause(self) -> None:
        self.pause_requested.emit()
        self._board_view.set_led_brightness("PWR", 0.0)
        self._run_state.setText("Estado: detenido")
        self._peripherals.set_editable(True)

    def _open_layout_editor(self) -> None:
        editor = BoardLayoutEditor(BoardLayout.load(bundled_layout()), self)
        if editor.exec():
            self.setWindowTitle("FPGALab · layout guardado; reinicie la vista para recargarlo")

    def _bouncy_input(self, name: str, final_value: int) -> None:
        """Three quick transitions make button bounce perceptible and configurable."""
        if name == "RESET":
            self.reset_requested.emit()
            return
        if name not in self._available_inputs:
            self._show_failure(f"{name}: no existe como entrada del perfil HDL")
            return
        values = [final_value, 1 - final_value, final_value]
        for index, value in enumerate(values):
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda v=value: self.set_input_requested.emit(name, v))
            timer.timeout.connect(timer.deleteLater)
            timer.start(index * 2)
            self._bounce_timers.append(timer)

    def _paint_state(self, leds: list, segments: int, gpio_out: int) -> None:
        for index, state in enumerate(leds):
            self._board_view.set_led_brightness(f"LED{index}", float(state))
        self._peripherals.update_gpio(gpio_out)

    def _show_failure(self, error: str) -> None:
        self.setWindowTitle(f"FPGALab · simulación detenida: {error}")

    def closeEvent(self, event) -> None:
        if self._thread.isRunning():
            QMetaObject.invokeMethod(self._worker, "shutdown", Qt.ConnectionType.BlockingQueuedConnection)
            self._thread.quit()
            if not self._thread.wait(3000):
                self._show_failure("esperando el cierre seguro de la simulación")
                event.ignore()
                return
        event.accept()
