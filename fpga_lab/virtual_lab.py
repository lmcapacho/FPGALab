"""Modern visual panel for interacting with an emulated Alhambra II."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QEvent, QMetaObject, QThread, QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import QApplication, QComboBox, QFrame, QHBoxLayout, QLabel, QKeySequenceEdit, QLineEdit, QMessageBox, QPushButton, QVBoxLayout, QWidget

from .board import BoardDefinition, bundled_board_definition
from .i18n import language_manager, t
from .lab_workspace import LabWorkspace
from .board_editor import BoardLayoutEditor
from .peripherals_panel import PeripheralsPanel
from .board_layout import BoardLayout, bundled_layout
from .board_view import BoardView
from .sink_bind import collect_vga_bindings
from .simulation import VerilatorSimulation
from .simulation_worker import SimulationFrame, SimulationWorker
from .wiring import VirtualLabProject

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
    configure_vga_requested = pyqtSignal(object)
    set_temporal_probes_requested = pyqtSignal(object)
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
        self.setWindowTitle(t("FPGALab · Virtual FPGA Lab"))
        self.setMinimumSize(800, 520)
        self.setStyleSheet(_QSS)
        self._bounce_timers: list[QTimer] = []
        self._simulation = simulation
        self._clock_hz = clock_hz
        self._ignore_state = False
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
        self._application = QApplication.instance()
        if self._application is not None:
            self._application.installEventFilter(self)

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
            self.configure_vga_requested.connect(self._worker.configure_vga_bindings)
            self.set_temporal_probes_requested.connect(self._worker.set_temporal_probes)
            self._worker.state_changed.connect(self._paint_state)
            self._worker.failure.connect(self._show_failure)
            self._worker.stopped.connect(self._thread.quit)
            self._thread.finished.connect(self._worker.deleteLater)
            self._peripherals.temporal_probes_changed.connect(self.set_temporal_probes_requested)
            self.set_temporal_probes_requested.emit(self._peripherals.temporal_probes())
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
        self._connections_button = QPushButton("🔌")
        self._connections_button.setFixedSize(30, 28)
        self._connections_button.clicked.connect(lambda: self._peripherals.open_connections())
        self._edit_layout_button = QPushButton("⚙")
        self._edit_layout_button.setFixedSize(30, 28)
        self._edit_layout_button.clicked.connect(self._open_layout_editor)
        board_header.addWidget(self._board_title)
        board_header.addStretch()
        board_header.addWidget(self._connections_button)
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
            dict(self._simulation.profile.outputs) if self._simulation else {},
        )
        self._peripherals.input_changed.connect(self.set_input_requested)
        gpio_layout.addWidget(self._peripherals, 1)
        controls.addWidget(gpio_panel, 1)
        root.addLayout(controls, 3)
        language_manager.language_changed.connect(self._retranslate_ui)
        self._retranslate_ui()

    def _retranslate_ui(self) -> None:
        self.setWindowTitle(t("FPGALab · Virtual FPGA Lab"))
        self._board_title.setText(f"{self._board_name.upper()} · {t('VIRTUAL FPGA')}")
        self._edit_layout_button.setToolTip(t("Edit board layout"))
        self._connections_button.setToolTip(t("View physical and HDL connections"))

    def workbench_zoom(self) -> float:
        """Return the current workbench zoom before this hosted lab is replaced."""
        return self._peripherals.workbench._zoom

    def set_workbench_zoom(self, zoom: float) -> None:
        """Restore the user's workbench framing after rebuilding a design."""
        self._peripherals.workbench.set_zoom(zoom)

    def stop_simulation(self) -> None:
        """Power off a clocked or combinational model from the main toolbar."""
        self._pause()

    def start_simulation(self) -> None:
        """Power on a clocked or combinational model after it is loaded."""
        self._play()

    def _play(self) -> None:
        bindings = ()
        if self._simulation is not None:
            project = VirtualLabProject.load(self._lab_file)
            bindings = collect_vga_bindings(project, self._peripherals.current_wires(), self._simulation.profile)
        if bindings and self._has_clock is not True:
            QMessageBox.warning(self, t("VGA monitor"), t("VGA monitor requires a clocked design."))
            self.status_changed.emit(t("VGA monitor requires a clocked design."))
            return
        if bindings and self._clock_hz == 12_000_000:
            self.status_changed.emit(t(
                "VGA 640×480 expects a ~25 MHz pixel clock; this lab is running at 12 MHz "
                "(Alhambra default). Use --clock-hz 25000000 or 25175000."
            ))
        self.configure_vga_requested.emit(bindings)
        if self._has_clock is True:
            self.play_requested.emit()
        self._board_view.set_led_brightness("PWR", 1.0)
        if not (bindings and self._clock_hz == 12_000_000):
            self.status_changed.emit(t("Simulation running.") if self._has_clock is True else t("Combinational logic active."))
        self._peripherals.set_editable(False)

    def _pause(self) -> None:
        self.pause_requested.emit()
        self._board_view.set_led_brightness("PWR", 0.0)
        self.status_changed.emit(t("Simulation stopped."))
        self._peripherals.set_editable(True)

    def _open_layout_editor(self) -> None:
        editor = BoardLayoutEditor(BoardLayout.load(bundled_layout()), self)
        if editor.exec():
            self.setWindowTitle(t("FPGALab · layout saved; restart the view to reload it"))

    def _bouncy_input(self, name: str, final_value: int) -> None:
        """Three quick transitions make button bounce perceptible and configurable."""
        if name == "RESET":
            self.reset_requested.emit()
            return
        port, bit = self._input_sources.get(name, (name, 0))
        if port not in self._available_inputs:
            # Physical controls remain available even when the current HDL
            # does not constrain or read them, exactly as on a real board.
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

    def _paint_state(self, frame: SimulationFrame) -> None:
        if self._ignore_state:
            return
        for index, state in enumerate(frame.led_brightness):
            self._board_view.set_led_brightness(f"LED{index}", float(state))
        self._peripherals.update_frame(frame)
        for snapshot in frame.sinks.values():
            if snapshot.seq and frame.virtual_hz:
                self.status_changed.emit(t(
                    "VGA 640×480 · frame {seq} · virtual {mhz:.1f} MHz",
                    seq=snapshot.seq,
                    mhz=frame.virtual_hz / 1e6,
                ))
                break

    def _show_failure(self, error: str) -> None:
        self.setWindowTitle(t("FPGALab · simulation stopped: {error}", error=error))
        self.status_changed.emit(t("Simulation error: {error}", error=error))

    def eventFilter(self, watched, event) -> bool:
        """Keep button shortcuts active while avoiding text-entry widgets."""
        if event.type() not in {QEvent.Type.KeyPress, QEvent.Type.KeyRelease} or not self.isVisible():
            return super().eventFilter(watched, event)
        focused = QApplication.focusWidget()
        if isinstance(focused, (QLineEdit, QComboBox, QKeySequenceEdit)):
            return super().eventFilter(watched, event)
        if self._peripherals.handle_shortcut_event(event, event.type() == QEvent.Type.KeyPress):
            return True
        return super().eventFilter(watched, event)

    def closeEvent(self, event) -> None:
        self._ignore_state = True
        if self._application is not None:
            self._application.removeEventFilter(self)
        if self._worker is not None:
            try:
                self._worker.state_changed.disconnect(self._paint_state)
            except TypeError:
                pass
        self._peripherals.drop_vga_images()
        if self._thread is not None and self._thread.isRunning():
            QMetaObject.invokeMethod(self._worker, "shutdown", Qt.ConnectionType.BlockingQueuedConnection)
            self._thread.quit()
            if not self._thread.wait(3000):
                self._show_failure(t("waiting for safe simulation shutdown"))
                event.ignore()
                return
        event.accept()
