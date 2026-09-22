"""Modern visual panel for interacting with an emulated Alhambra II."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QEvent, QSettings, QThread, QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import QApplication, QAbstractSpinBox, QComboBox, QFrame, QHBoxLayout, QLabel, QKeySequenceEdit, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QSplitter, QTextEdit, QVBoxLayout, QWidget

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
from .theme import Metrics, style_button


_PANEL_SPLIT_KEY = "ui/board_workbench_ratio"
_DEFAULT_PANEL_SPLIT = 0.3


def _panel_split_ratio(settings: QSettings) -> float:
    """Read a safe per-user board/workbench width ratio."""
    try:
        ratio = float(settings.value(_PANEL_SPLIT_KEY, _DEFAULT_PANEL_SPLIT))
    except (TypeError, ValueError):
        return _DEFAULT_PANEL_SPLIT
    return min(0.75, max(0.2, ratio))


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
    clock_performance_changed = pyqtSignal(float, float)

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
        settings: QSettings | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(t("FPGALab · Virtual FPGA Lab"))
        self.setMinimumSize(800, 520)
        self._bounce_timers: list[QTimer] = []
        self._simulation = simulation
        self._clock_hz = clock_hz
        self._running = False
        self._ignore_state = False
        self._board_name = simulation.profile.board_name if simulation else "Alhambra II"
        self._available_inputs = frozenset(simulation.profile.inputs) if simulation else frozenset()
        self._has_clock = simulation.profile.clock_name is not None if simulation else None
        self._input_widths = dict(simulation.profile.inputs) if simulation else {}
        self._led_sources = led_sources
        self._input_sources = input_sources or {}
        self._settings = settings if settings is not None else QSettings("FPGALab", "FPGALab")
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
            self._thread.finished.connect(self._worker.deleteLater)
            self._peripherals.temporal_probes_changed.connect(self.set_temporal_probes_requested)
            self.set_temporal_probes_requested.emit(self._peripherals.temporal_probes())
            self._thread.start()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setObjectName("labSplitter")
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setHandleWidth(7)
        outer.addWidget(self._splitter)
        self._board_panel = QFrame(objectName="boardPanel")
        self._board_panel.setMinimumWidth(240)
        board_layout = QVBoxLayout(self._board_panel)
        board_layout.setContentsMargins(Metrics.SPACE_MD, Metrics.SPACE_MD, Metrics.SPACE_MD, Metrics.SPACE_MD)
        board_header = QHBoxLayout()
        self._board_title = QLabel()
        self._board_title.setObjectName("boardTitle")
        self._connections_button = QPushButton()
        style_button(self._connections_button, "icon", "connections")
        self._connections_button.clicked.connect(lambda: self._peripherals.open_connections())
        self._edit_layout_button = QPushButton()
        style_button(self._edit_layout_button, "icon", "edit")
        self._edit_layout_button.clicked.connect(self._open_layout_editor)
        board_header.addWidget(self._board_title)
        board_header.addStretch()
        board_header.addWidget(self._connections_button)
        board_header.addWidget(self._edit_layout_button)
        board_layout.addLayout(board_header)
        self._board_view = BoardView(self._layout, self._bouncy_input)
        board_layout.addWidget(self._board_view, 1)
        self._splitter.addWidget(self._board_panel)
        gpio_panel = QFrame(objectName="panel")
        gpio_layout = QVBoxLayout(gpio_panel)
        gpio_layout.setContentsMargins(0, 0, 0, 0)
        self._peripherals = PeripheralsPanel(
            BoardDefinition.load(bundled_board_definition()),
            self._project_pcf,
            self._lab_file,
            self._input_widths,
            dict(self._simulation.profile.outputs) if self._simulation else {},
        )
        self._peripherals.input_changed.connect(self.set_input_requested)
        self._peripherals.changed.connect(self.status_changed.emit)
        gpio_layout.addWidget(self._peripherals, 1)
        self._splitter.addWidget(gpio_panel)
        ratio = _panel_split_ratio(self._settings)
        self._splitter.setSizes([round(ratio * 1000), round((1.0 - ratio) * 1000)])
        self._splitter.splitterMoved.connect(self._save_panel_split)
        language_manager.language_changed.connect(self._retranslate_ui)
        self._retranslate_ui()

    def _save_panel_split(self, _position: int, _index: int) -> None:
        """Persist the divider as a ratio so it survives window-size changes."""
        sizes = self._splitter.sizes()
        total = sum(sizes)
        if total <= 0:
            return
        ratio = min(0.75, max(0.2, sizes[0] / total))
        self._settings.setValue(_PANEL_SPLIT_KEY, ratio)
        self._settings.sync()

    def _retranslate_ui(self) -> None:
        self.setWindowTitle(t("FPGALab · Virtual FPGA Lab"))
        self._refresh_board_title()
        self._edit_layout_button.setToolTip(t("Edit board layout"))
        self._connections_button.setToolTip(t("View physical and HDL connections"))

    def _refresh_board_title(self) -> None:
        """Use a compact board title when toolbar actions need the available width."""
        board_name = self._board_name.upper()
        full_title = f"{board_name} · {t('VIRTUAL FPGA')}"
        button_width = self._connections_button.width() + self._edit_layout_button.width()
        available = max(0, self._board_panel.width() - button_width - 44)
        title = full_title if self._board_title.fontMetrics().horizontalAdvance(full_title) <= available else board_name
        self._board_title.setText(title)
        self._board_title.setToolTip(full_title)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._refresh_board_title()

    def workbench_zoom(self) -> float:
        """Return the current workbench zoom before this hosted lab is replaced."""
        return self._peripherals.workbench._zoom

    def requested_clock_hz(self) -> float | None:
        """Return the active clock target, or none for combinational HDL."""
        return float(self._clock_hz) if self._has_clock is True else None

    def set_workbench_zoom(self, zoom: float) -> None:
        """Restore the user's workbench framing after rebuilding a design."""
        self._peripherals.workbench.set_zoom(zoom)

    def workbench_history(self):
        """Return the active Lab editing history before replacing this widget."""
        return self._peripherals.history_state()

    def restore_workbench_history(self, state) -> None:
        """Restore editing history after attaching a newly compiled simulation."""
        self._peripherals.restore_history_state(state)

    def refresh_theme(self) -> None:
        """Apply the active semantic palette to custom-painted Lab surfaces."""
        self._board_view.refresh_theme()
        self._peripherals.refresh_theme()
        self.update()

    def set_lab_file(self, lab_file: str | Path) -> None:
        """Load another laboratory without rebuilding the active HDL model."""
        self._lab_file = Path(lab_file)
        self._peripherals.set_lab_file(self._lab_file)
        if self._simulation is not None:
            project = VirtualLabProject.load(self._lab_file)
            bindings = collect_vga_bindings(project, self._peripherals.current_wires(), self._simulation.profile)
            self.configure_vga_requested.emit(bindings)

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
            status = t(
                "VGA 640×480 expects a ~25 MHz pixel clock; this lab is running at 12 MHz "
                "(Alhambra default). Use --clock-hz 25000000 or 25175000."
            )
        else:
            status = t("Simulation running.") if self._has_clock is True else t("Combinational logic active.")
        self.configure_vga_requested.emit(bindings)
        # Combinational designs still need periodic visual frames so static
        # outputs can contribute to the peripheral persistence models.
        self._running = True
        self._peripherals.set_powered(True)
        self.play_requested.emit()
        self._board_view.set_led_brightness("PWR", 1.0)
        self._edit_layout_button.setEnabled(False)
        missing = self._peripherals.missing_required_connections()
        if missing:
            status += " " + t(
                "{count} required peripheral terminal(s) are not connected: {terminals}.",
                count=len(missing),
                terminals=", ".join(missing),
            )
        self.status_changed.emit(status)
        self._peripherals.set_editable(False)

    def _pause(self) -> None:
        # Ignore frames already queued by the worker before Stop was pressed.
        self._running = False
        self._peripherals.set_powered(False)
        self.pause_requested.emit()
        self._board_view.clear_leds()
        self._edit_layout_button.setEnabled(True)
        self.status_changed.emit(t("Simulation stopped."))
        self._peripherals.set_editable(True)

    def _open_layout_editor(self) -> None:
        editor = BoardLayoutEditor(BoardLayout.load(bundled_layout()), self)
        if editor.exec():
            self.setWindowTitle(t("FPGALab · layout saved; restart the view to reload it"))

    def _bouncy_input(self, name: str, final_value: int) -> None:
        """Three quick transitions make button bounce perceptible and configurable."""
        if not self._running:
            return
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
        if not self._running:
            return
        current = self._board_input_values.get(port, 0)
        current = current | (1 << bit) if value else current & ~(1 << bit)
        self._board_input_values[port] = current
        self.set_input_requested.emit(port, current)

    def _paint_state(self, frame: SimulationFrame) -> None:
        if self._ignore_state or not self._running:
            return
        for index, state in enumerate(frame.led_brightness):
            self._board_view.set_led_brightness(f"LED{index}", float(state))
        self._peripherals.update_frame(frame)
        if self._running and self._has_clock is True and frame.virtual_hz > 0.0:
            self.clock_performance_changed.emit(float(self._clock_hz), frame.virtual_hz)
        for snapshot in frame.sinks.values():
            if snapshot.seq and frame.virtual_hz:
                self.status_changed.emit(t(
                    "VGA 640×480 · frame {seq} · virtual {mhz:.1f} MHz",
                    seq=snapshot.seq,
                    mhz=frame.virtual_hz / 1e6,
                ))
                break

    def _show_failure(self, error: str) -> None:
        self._running = False
        self._peripherals.set_powered(False)
        self.setWindowTitle(t("FPGALab · simulation stopped: {error}", error=error))
        self.status_changed.emit(t("Simulation error: {error}", error=error))

    def eventFilter(self, watched, event) -> bool:
        """Keep button shortcuts active while avoiding text-entry widgets."""
        if event.type() not in {QEvent.Type.KeyPress, QEvent.Type.KeyRelease} or not self.isVisible():
            return super().eventFilter(watched, event)
        focused = QApplication.focusWidget()
        if event.type() == QEvent.Type.KeyRelease and self._peripherals.handle_shortcut_event(event, False):
            return True
        if focused is None or focused.window() is not self.window() or isinstance(
            focused, (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox, QComboBox, QKeySequenceEdit)
        ):
            return super().eventFilter(watched, event)
        if event.type() == QEvent.Type.KeyPress and self._peripherals.handle_shortcut_event(event, True):
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
            self.shutdown_requested.emit()
            if not self._thread.wait(3000):
                self._show_failure(t("waiting for safe simulation shutdown"))
                event.ignore()
                return
        event.accept()
