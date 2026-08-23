"""Modern visual panel for interacting with an emulated Alhambra II."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QMetaObject, QThread, QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .board import BoardDefinition, bundled_board_definition
from .i18n import language_manager, t
from .lab_workspace import LabWorkspace
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


class FPGAVirtualLab(QWidget):
    """Embeddable window. Signals reach the worker through queued Qt slots."""

    set_input_requested = pyqtSignal(str, int)
    shutdown_requested = pyqtSignal()
    play_requested = pyqtSignal()
    pause_requested = pyqtSignal()
    reset_requested = pyqtSignal()
    status_changed = pyqtSignal(str)

    def __init__(
        self,
        simulation: VerilatorSimulation | None = None,
        clock_hz: int = 12_000_000,
        ui_refresh_hz: int = 60,
        observation_hz: int = 1_000_000,
        project_pcf: Path | None = None,
        lab_file: Path | None = None,
        led_sources: dict[int, tuple[str, int]] | None = None,
        input_sources: dict[str, tuple[str, int]] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(t("FPGALab · Virtual FPGA Lab", "FPGALab · Laboratorio Virtual"))
        self.setMinimumSize(800, 520)
        self.setStyleSheet(_QSS)
        self._bounce_timers: list[QTimer] = []
        self._simulation = simulation
        self._board_name = simulation.profile.board_name if simulation else "Alhambra II"
        self._available_inputs = frozenset(simulation.profile.inputs) if simulation else frozenset()
        self._has_clock = simulation.profile.clock_name is not None if simulation else None
        self._input_widths = dict(simulation.profile.inputs) if simulation else {}
        self._led_sources = led_sources
        self._input_sources = input_sources or {}
        self._board_input_values: dict[str, int] = {}
        self._layout = BoardLayout.load(bundled_layout())
        self._project_pcf = project_pcf
        self._lab_file = lab_file or LabWorkspace().ensure_default()
        self._build_ui()

        self._thread: QThread | None = None
        self._worker: SimulationWorker | None = None
        if simulation is not None:
            self._thread = QThread(self)
            self._worker = SimulationWorker(simulation, clock_hz, ui_refresh_hz, observation_hz, self._led_sources)
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
        outer.setContentsMargins(0, 0, 0, 0)
        root = QHBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        outer.addLayout(root)
        board_panel = QFrame(objectName="board")
        board_panel.setMinimumWidth(300)
        board_layout = QVBoxLayout(board_panel)
        board_header = QHBoxLayout()
        self._board_title = QLabel()
        self._board_title.setStyleSheet("font-size: 20px; font-weight: 800; color:#bbf7d0;")
        self._edit_layout_button = QPushButton("⚙")
        self._edit_layout_button.setFixedSize(30, 28)
        self._edit_layout_button.clicked.connect(self._open_layout_editor)
        board_header.addWidget(self._board_title)
        board_header.addStretch()
        board_header.addWidget(self._edit_layout_button)
        board_layout.addLayout(board_header)
        self._board_view = BoardView(self._layout, self._bouncy_input)
        board_layout.addWidget(self._board_view, 1)
        root.addWidget(board_panel, 2)

        controls = QVBoxLayout()
        gpio_panel = QFrame(objectName="panel")
        gpio_layout = QVBoxLayout(gpio_panel)
        self._peripherals = PeripheralsPanel(
            BoardDefinition.load(bundled_board_definition()),
            self._project_pcf,
            self._lab_file,
            self._input_widths,
        )
        self._peripherals.input_changed.connect(self.set_input_requested)
        gpio_layout.addWidget(self._peripherals, 1)
        controls.addWidget(gpio_panel, 1)
        root.addLayout(controls, 3)
        language_manager.language_changed.connect(self._retranslate_ui)
        self._retranslate_ui()

    def _retranslate_ui(self) -> None:
        self.setWindowTitle(t("FPGALab · Virtual FPGA Lab", "FPGALab · Laboratorio Virtual"))
        self._board_title.setText(f"{self._board_name.upper()} · {t('VIRTUAL FPGA', 'FPGA VIRTUAL')}")
        self._edit_layout_button.setToolTip(t("Edit board layout", "Editar layout de la placa"))

    def stop_simulation(self) -> None:
        """Stop a clocked simulation from the main project toolbar."""
        if self._has_clock is True:
            self._pause()

    def start_simulation(self) -> None:
        """Start a clocked simulation after the project has been loaded."""
        if self._has_clock is True:
            self._play()

    def _play(self) -> None:
        self.play_requested.emit()
        self._board_view.set_led_brightness("PWR", 1.0)
        self.status_changed.emit(t("Simulation running.", "Simulación ejecutando."))
        self._peripherals.set_editable(False)

    def _pause(self) -> None:
        self.pause_requested.emit()
        self._board_view.set_led_brightness("PWR", 0.0)
        self.status_changed.emit(t("Simulation stopped.", "Simulación detenida."))
        self._peripherals.set_editable(True)

    def _open_layout_editor(self) -> None:
        editor = BoardLayoutEditor(BoardLayout.load(bundled_layout()), self)
        if editor.exec():
            self.setWindowTitle(t("FPGALab · layout saved; restart the view to reload it", "FPGALab · layout guardado; reinicie la vista para recargarlo"))

    def _bouncy_input(self, name: str, final_value: int) -> None:
        """Three quick transitions make button bounce perceptible and configurable."""
        if name == "RESET":
            self.reset_requested.emit()
            return
        port, bit = self._input_sources.get(name, (name, 0))
        if port not in self._available_inputs:
            self._show_failure(t("{name}: not connected by the current HDL", "{name}: no está conectado en el HDL actual", name=name))
            return
        values = [final_value, 1 - final_value, final_value]
        for index, value in enumerate(values):
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda v=value, p=port, b=bit: self._set_board_input(p, b, v))
            timer.timeout.connect(timer.deleteLater)
            timer.start(index * 2)
            self._bounce_timers.append(timer)

    def _set_board_input(self, port: str, bit: int, value: int) -> None:
        current = self._board_input_values.get(port, 0)
        current = current | (1 << bit) if value else current & ~(1 << bit)
        self._board_input_values[port] = current
        self.set_input_requested.emit(port, current)

    def _paint_state(self, leds: list, segments: int, gpio_out: int, outputs: dict[str, int]) -> None:
        for index, state in enumerate(leds):
            self._board_view.set_led_brightness(f"LED{index}", float(state))
        self._peripherals.update_outputs(outputs)

    def _show_failure(self, error: str) -> None:
        self.setWindowTitle(t("FPGALab · simulation stopped: {error}", "FPGALab · simulación detenida: {error}", error=error))
        self.status_changed.emit(t("Simulation error: {error}", "Error de simulación: {error}", error=error))

    def closeEvent(self, event) -> None:
        if self._thread is not None and self._thread.isRunning():
            QMetaObject.invokeMethod(self._worker, "shutdown", Qt.ConnectionType.BlockingQueuedConnection)
            self._thread.quit()
            if not self._thread.wait(3000):
                self._show_failure(t("waiting for safe simulation shutdown", "esperando el cierre seguro de la simulación"))
                event.ignore()
                return
        event.accept()
