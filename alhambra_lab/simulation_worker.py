"""Ejecución del modelo fuera del hilo de la interfaz Qt."""

from __future__ import annotations

from time import perf_counter

from PyQt6.QtCore import QObject, QTimer, Qt, pyqtSignal, pyqtSlot

from .simulation import VerilatorSimulation


class SimulationWorker(QObject):
    """Avanza N ciclos por frame y publica solo el estado necesario para pintar."""

    state_changed = pyqtSignal(list, int, int)  # leds, segments, gpio_out
    failure = pyqtSignal(str)
    stopped = pyqtSignal()

    def __init__(self, simulation: VerilatorSimulation, ticks_per_frame: int = 12_000):
        super().__init__()
        self._simulation = simulation
        self._ticks_per_frame = ticks_per_frame
        self._timer: QTimer | None = None

    @pyqtSlot()
    def start(self) -> None:
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(1)  # Qt lo limita según SO; el modelo vive fuera de la GUI.
        self._timer.timeout.connect(self._run_frame)
        self._timer.start()

    @pyqtSlot()
    def _run_frame(self) -> None:
        try:
            started = perf_counter()
            self._simulation.ticks(self._ticks_per_frame)
            leds = self._simulation.read_leds()
            segments = self._simulation.get_output("segments") if "segments" in self._simulation.profile.outputs else 0
            gpio_out = self._simulation.get_output("gpio_out") if "gpio_out" in self._simulation.profile.outputs else 0
            self.state_changed.emit(leds, segments, gpio_out)
            # Si una máquina no sostiene el presupuesto, evita que el hilo se
            # monopolice: reduce gradualmente ciclos, conservando interactividad.
            if perf_counter() - started > 0.012 and self._ticks_per_frame > 100:
                self._ticks_per_frame = max(100, int(self._ticks_per_frame * 0.8))
        except Exception as exc:  # Evita que una excepción silenciosa mate el hilo Qt.
            if self._timer:
                self._timer.stop()
            self.failure.emit(str(exc))

    @pyqtSlot(str, int)
    def set_input(self, name: str, value: int) -> None:
        self._simulation.set_input(name, value)

    @pyqtSlot()
    def shutdown(self) -> None:
        if self._timer:
            self._timer.stop()
        self._simulation.close()
        self.stopped.emit()
