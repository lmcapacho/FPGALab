"""Virtual-clock execution outside the Qt interface thread."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter

from PyQt6.QtCore import QObject, QTimer, Qt, pyqtSignal, pyqtSlot

from .i18n import t
from .simulation import VgaStats, VerilatorSimulation
from .sink_bind import VgaBinding
from .temporal import LedModel


@dataclass(frozen=True)
class VgaSnapshot:
    kind: str = "vga"
    seq: int = 0
    width: int = 0
    height: int = 0
    pixels: bytes | None = None
    stats: VgaStats | None = None
    missing_required: tuple[str, ...] = ()
    bind_errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class TemporalFrame:
    """Native predicate summaries for declarative temporal peripherals."""

    hits: tuple[int, ...] = ()
    samples: int = 0
    ends: tuple[bool, ...] = ()
    edges: tuple[int, ...] = ()
    elapsed_seconds: float = 0.0


@dataclass(frozen=True)
class SimulationFrame:
    led_brightness: tuple[float, ...]
    outputs: dict[str, int]
    sinks: dict[str, VgaSnapshot] = field(default_factory=dict)
    virtual_hz: float = 0.0
    cycles: int = 0
    temporal: TemporalFrame = field(default_factory=TemporalFrame)


class SimulationWorker(QObject):
    """Maintain the virtual clock and publish state only at visual frequency."""

    state_changed = pyqtSignal(object)
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
            raise ValueError(t("clock_hz, ui_refresh_hz, and observation_hz must be positive."))
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
        self._vga_bindings: tuple[VgaBinding, ...] = ()
        self._sink_id: int | None = None
        self._blank_next = False
        self._temporal_probes: tuple[tuple[tuple[int, int, bool], ...], ...] = ()

    @pyqtSlot()
    def start(self) -> None:
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(max(1, round(1000 / self._ui_refresh_hz)))
        self._timer.timeout.connect(self._run_frame)
        self._last_frame_time = perf_counter()
        if self._simulation.profile.clock_name is None:
            self._run_frame()

    @pyqtSlot(object)
    def configure_vga_bindings(self, bindings) -> None:
        bindings = tuple(bindings or ())
        if bindings == self._vga_bindings and self._sink_id is not None:
            return
        if self._sink_id is not None:
            self._simulation.destroy_vga(self._sink_id)
            self._sink_id = None
        self._vga_bindings = bindings
        if not bindings:
            return
        if len(bindings) > 1:
            self.failure.emit(t("Only one VGA monitor is supported in this version."))
            return
        try:
            self._sink_id = self._simulation.configure_vga(bindings[0].timing, bindings[0].channels)
        except Exception as exc:
            self.failure.emit(str(exc))

    @pyqtSlot(object)
    def set_temporal_probes(self, probes) -> None:
        """Install generic output predicates configured by the workbench catalog."""
        try:
            self._temporal_probes = tuple(tuple(tuple(term) for term in probe) for probe in (probes or ()))
            self._simulation.set_temporal_probes(list(self._temporal_probes))
        except Exception as exc:
            self.failure.emit(str(exc))

    @pyqtSlot()
    def play(self) -> None:
        if self._timer and not self._timer.isActive():
            self._last_frame_time = perf_counter()
            self._cycle_remainder = 0.0
            self._blank_next = False
            self._timer.start()

    @pyqtSlot()
    def pause(self) -> None:
        if self._timer:
            self._timer.stop()

    @pyqtSlot()
    def power_off(self) -> None:
        self.pause()
        self._simulation.reset()
        self._simulation.streaming_reset()
        self._blank_next = True
        self.state_changed.emit(SimulationFrame(
            led_brightness=tuple([0.0] * 8),
            outputs={},
            sinks=self._blank_sinks(),
            temporal=TemporalFrame(),
        ))

    def _blank_sinks(self) -> dict[str, VgaSnapshot]:
        return {
            binding.peripheral_id: VgaSnapshot(
                seq=0,
                pixels=b"",
                missing_required=binding.missing_required,
                bind_errors=binding.bind_errors,
            )
            for binding in self._vga_bindings
        }

    def _keep_sinks(self) -> dict[str, VgaSnapshot]:
        snapshots = {}
        for binding in self._vga_bindings:
            copied = None
            if self._sink_id is not None:
                copied = self._simulation.vga_copy_front(
                    self._sink_id, binding.timing.h_active, binding.timing.v_active
                )
            if copied is None:
                snapshots[binding.peripheral_id] = VgaSnapshot(
                    seq=0,
                    pixels=None,
                    missing_required=binding.missing_required,
                    bind_errors=binding.bind_errors,
                )
                continue
            pixels, stats = copied
            snapshots[binding.peripheral_id] = VgaSnapshot(
                seq=stats.seq,
                width=binding.timing.h_active,
                height=binding.timing.v_active,
                pixels=pixels,
                stats=stats,
                missing_required=binding.missing_required,
                bind_errors=binding.bind_errors,
            )
        return snapshots

    @pyqtSlot()
    def _run_frame(self) -> None:
        try:
            now = perf_counter()
            elapsed = min(now - self._last_frame_time, 0.100)
            self._last_frame_time = now
            exact_cycles = elapsed * self._clock_hz + self._cycle_remainder
            cycles = int(exact_cycles)
            self._cycle_remainder = exact_cycles - cycles
            self._simulation.ticks(cycles)
            windows = self._simulation.observed_windows(cycles)
            temporal_hits, temporal_samples, temporal_ends, temporal_edges = self._simulation.temporal_probe_window()
            virtual_elapsed = cycles / self._clock_hz if self._clock_hz else 0.0
            leds = []
            for index, model in enumerate(self._led_models):
                port, bit = self._led_sources.get(index, (f"LED{index}", 0))
                signal = windows.get(f"{port}[{bit}]")
                leds.append(model.advance({"anode": signal}, virtual_elapsed) if signal else 0.0)
            outputs = {
                name: self._simulation.get_output(name)
                for name in self._simulation.profile.outputs
            }
            virtual_hz = cycles / elapsed if elapsed else 0.0
            self.state_changed.emit(SimulationFrame(
                led_brightness=tuple(leds),
                outputs=outputs,
                sinks=self._keep_sinks(),
                virtual_hz=virtual_hz,
                cycles=cycles,
                temporal=TemporalFrame(
                    tuple(temporal_hits), temporal_samples, tuple(temporal_ends), tuple(temporal_edges), virtual_elapsed
                ),
            ))
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
        self._simulation.streaming_reset()
        if was_running:
            self.play()
        elif self._simulation.profile.clock_name is None:
            self._run_frame()

    @pyqtSlot(str, int)
    def set_input(self, name: str, value: int) -> None:
        try:
            self._simulation.set_input(name, value)
            if self._simulation.profile.clock_name is None:
                self._run_frame()
        except Exception as exc:
            self.failure.emit(str(exc))

    @pyqtSlot()
    def shutdown(self) -> None:
        if self._timer:
            self._timer.stop()
        self._simulation.close()
        self.stopped.emit()
