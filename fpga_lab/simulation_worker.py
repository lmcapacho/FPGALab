"""Virtual-clock execution outside the Qt interface thread."""

from __future__ import annotations

from time import perf_counter

from PyQt6.QtCore import QObject, QTimer, Qt, pyqtSignal, pyqtSlot

from .i18n import t
from .simulation import VerilatorSimulation
from .temporal import LedModel


class SimulationWorker(QObject):
    """Maintain the virtual clock and publish state only at visual frequency."""

    state_changed = pyqtSignal(list, int, int, dict)  # LED brightness, segments, gpio_out, HDL outputs
    failure = pyqtSignal(str)
    stopped = pyqtSignal()

    def __init__(
        self,
        simulation: VerilatorSimulation,
        clock_hz: int = 12_000_000,
        ui_refresh_hz: int = 60,
        observation_hz: int = 1_000_000,
        led_sources: dict[int, tuple[str, int]] | None = None,
    ):
        super().__init__()
        if clock_hz <= 0 or ui_refresh_hz <= 0 or observation_hz <= 0:
            raise ValueError(t("clock_hz, ui_refresh_hz, and observation_hz must be positive.", "clock_hz, ui_refresh_hz y observation_hz deben ser positivos."))
        self._simulation = simulation
        self._clock_hz = clock_hz
        self._ui_refresh_hz = ui_refresh_hz
        self._observation_hz = observation_hz
        self._simulation.set_observation_divisor(max(1, (clock_hz + observation_hz - 1) // observation_hz))
        self._timer: QTimer | None = None
        self._last_frame_time = 0.0
        self._cycle_remainder = 0.0
        self._led_models = [LedModel() for _ in range(8)]
        self._led_sources = led_sources or {index: (f"LED{index}", 0) for index in range(8)}

    @pyqtSlot()
    def start(self) -> None:
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(max(1, round(1000 / self._ui_refresh_hz)))
        self._timer.timeout.connect(self._run_frame)
        self._last_frame_time = perf_counter()
        if self._simulation.profile.clock_name is None:
            self._run_frame()

    @pyqtSlot()
    def play(self) -> None:
        if self._timer and not self._timer.isActive():
            self._last_frame_time = perf_counter()
            self._cycle_remainder = 0.0
            self._timer.start()

    @pyqtSlot()
    def pause(self) -> None:
        if self._timer:
            self._timer.stop()

    @pyqtSlot()
    def power_off(self) -> None:
        self.pause()
        self._simulation.reset()
        self.state_changed.emit([0.0] * 8, 0, 0, {})

    @pyqtSlot()
    def _run_frame(self) -> None:
        try:
            now = perf_counter()
            # Prevent a debugger pause from producing an enormous burst.
            elapsed = min(now - self._last_frame_time, 0.100)
            self._last_frame_time = now
            exact_cycles = elapsed * self._clock_hz + self._cycle_remainder
            cycles = int(exact_cycles)
            self._cycle_remainder = exact_cycles - cycles
            self._simulation.ticks(cycles)
            windows = self._simulation.observed_windows(cycles)
            virtual_elapsed = cycles / self._clock_hz
            leds = []
            for index, model in enumerate(self._led_models):
                port, bit = self._led_sources.get(index, (f"LED{index}", 0))
                signal = windows.get(f"{port}[{bit}]")
                leds.append(model.advance({"anode": signal}, virtual_elapsed) if signal else 0.0)
            outputs = {
                name: self._simulation.get_output(name)
                for name in self._simulation.profile.outputs
            }
            segments = outputs.get("segments", 0)
            gpio_out = outputs.get("gpio_out", 0)
            self.state_changed.emit(leds, segments, gpio_out, outputs)
        except Exception as exc:
            if self._timer:
                self._timer.stop()
            self.failure.emit(str(exc))

    @pyqtSlot()
    def reset(self) -> None:
        was_running = bool(self._timer and self._timer.isActive())
        if self._timer:
            self._timer.stop()
        self._simulation.reset()
        if was_running:
            self.play()

    @pyqtSlot(str, int)
    def set_input(self, name: str, value: int) -> None:
        try:
            self._simulation.set_input(name, value)
        except Exception as exc:
            self.failure.emit(str(exc))

    @pyqtSlot()
    def shutdown(self) -> None:
        if self._timer:
            self._timer.stop()
        self._simulation.close()
        self.stopped.emit()
