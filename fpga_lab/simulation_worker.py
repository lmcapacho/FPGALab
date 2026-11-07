"""Qt scheduling/signals adapter for the framework-free simulation engine."""

from time import perf_counter

from PyQt6.QtCore import QObject, QThread, QTimer, Qt, pyqtSignal, pyqtSlot

from .board import bundled_board_clock_hz
from .i18n import t
from .simulation import VerilatorSimulation
# Re-export existing frame imports for compatibility with GUI consumers.
from .simulation_engine import (
    SimulationEngine, SimulationFrame, TemporalFrame, EdgeFrame, VgaSnapshot,
    effective_virtual_hz, pulse_samples_to_seconds,
)


class SimulationWorker(QObject):
    """Own the Qt timer; all native execution belongs to the engine."""

    state_changed = pyqtSignal(object)
    failure = pyqtSignal(str)
    notice = pyqtSignal(str)
    uart_send_result = pyqtSignal(int, str, bool)
    stopped = pyqtSignal()

    def __init__(self, simulation: VerilatorSimulation,
                 clock_hz: int = bundled_board_clock_hz(), ui_refresh_hz: int = 60,
                 observation_hz: int = 1_000_000,
                 led_sources: dict[int, tuple[str, int]] | None = None,
                 led_endpoints: tuple[str, ...] | None = None,
                 led_active_low: tuple[bool, ...] = (), *, engine: SimulationEngine | None = None):
        super().__init__()
        if ui_refresh_hz <= 0:
            raise ValueError(t("clock_hz, ui_refresh_hz, and observation_hz must be positive."))
        self._engine = engine if engine is not None else SimulationEngine(
            simulation, clock_hz, observation_hz=observation_hz, led_sources=led_sources,
            led_endpoints=tuple(led_endpoints or ()), led_active_low=led_active_low)
        self._ui_refresh_hz = ui_refresh_hz
        self._timer: QTimer | None = None
        self._last_frame_time = 0.0

    def _publish(self, frame: SimulationFrame | None) -> None:
        if frame is not None:
            self.state_changed.emit(frame)

    def _call(self, operation, *args, notice=False) -> None:
        try:
            operation(*args)
        except Exception as exc:
            (self.notice if notice else self.failure).emit(str(exc))

    @pyqtSlot()
    def start(self) -> None:
        if self._timer is not None:
            return
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(max(1, round(1000 / self._ui_refresh_hz)))
        self._timer.timeout.connect(self._run_frame)
        self._last_frame_time = perf_counter()
        self._call(lambda: self._publish(self._engine.refresh()))

    @pyqtSlot(object)
    def configure_vga_bindings(self, bindings) -> None:
        self._call(self._engine.configure_vga_bindings, bindings)

    @pyqtSlot(object)
    def set_temporal_probes(self, probes) -> None:
        self._call(self._engine.set_temporal_probes, probes)

    @pyqtSlot(object)
    def configure_edge_channels(self, channels) -> None:
        self._call(self._engine.configure_edge_channels, channels)

    @pyqtSlot(object)
    def configure_drive_channels(self, channels) -> None:
        self._call(self._engine.configure_drive_channels, channels, notice=True)

    @pyqtSlot(object)
    def configure_spi_slaves(self, bindings) -> None:
        self._call(self._engine.configure_spi_slaves, bindings, notice=True)

    @pyqtSlot(int, int, str)
    def send_uart(self, channel: int, baud: int, text: str) -> None:
        try:
            count = self._engine.send_uart(channel, baud, text)
            if count:
                self.notice.emit(t("Queued {count} UART byte(s).", count=count))
                self.uart_send_result.emit(channel, text, True)
        except (ValueError, RuntimeError, UnicodeError) as exc:
            self.notice.emit(str(exc))
            self.uart_send_result.emit(channel, text, False)

    @pyqtSlot()
    def play(self) -> None:
        if self._timer and not self._timer.isActive():
            try:
                self._engine.play()
                self._last_frame_time = perf_counter()
                self._timer.start()
            except Exception as exc:
                self.failure.emit(str(exc))

    @pyqtSlot()
    def pause(self) -> None:
        if self._timer:
            self._timer.stop()
        self._engine.pause()

    @pyqtSlot()
    def power_off(self) -> None:
        self.pause()
        self._call(lambda: self._publish(self._engine.power_off()))

    @pyqtSlot()
    def _run_frame(self) -> None:
        try:
            now = perf_counter()
            elapsed = max(0.0, now - self._last_frame_time)
            self._last_frame_time = now
            self._publish(self._engine.advance(elapsed))
        except Exception as exc:
            self.pause()
            self.failure.emit(str(exc))

    @pyqtSlot()
    def reset(self) -> None:
        if self._timer:
            self._timer.stop()
        try:
            self._publish(self._engine.reset())
            if self._timer and self._engine.running:
                self._last_frame_time = perf_counter()
                self._timer.start()
        except Exception as exc:
            self.failure.emit(str(exc))

    @pyqtSlot(str, int)
    def set_input(self, name: str, value: int) -> None:
        self._call(lambda: self._publish(self._engine.set_input(name, value)))

    @pyqtSlot()
    def shutdown(self) -> None:
        self.pause()
        try:
            self._engine.close()
        except Exception as exc:
            self.failure.emit(str(exc))
        finally:
            self.stopped.emit()
            QThread.currentThread().quit()
