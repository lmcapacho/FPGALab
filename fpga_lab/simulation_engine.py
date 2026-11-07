"""Single-owner execution and frames without GUI, timers or event loops.

The host supplies elapsed wall time and schedules calls on one owner thread.
Native FPGA cycles stay batched; exceptions propagate to that host.
"""

from dataclasses import dataclass, field
import math

from .edge_drive import TimedDriveScheduler
from .messages import t
from .simulation import EdgeEvent, VgaStats, VerilatorSimulation
from .sink_bind import VgaBinding
from .serial_edges import uart_8n1_drive_events
from .temporal import LedModel, SignalWindow


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
    """Native predicate summaries measured in virtual time."""

    hits: tuple[int, ...] = ()
    samples: int = 0
    ends: tuple[bool, ...] = ()
    edges: tuple[int, ...] = ()
    elapsed_seconds: float = 0.0
    pulse_high_seconds: tuple[float | None, ...] = ()


@dataclass(frozen=True)
class EdgeFrame:
    """Transitions in virtual-cycle order; overflow invalidates the batch."""

    cycle: int = 0
    clock_hz: int = 0
    events: tuple[EdgeEvent, ...] = ()
    dropped: int = 0


@dataclass(frozen=True)
class SimulationFrame:
    led_brightness: tuple[float, ...]
    outputs: dict[str, int]
    sinks: dict[str, VgaSnapshot] = field(default_factory=dict)
    virtual_hz: float = 0.0
    cycles: int = 0
    temporal: TemporalFrame = field(default_factory=TemporalFrame)
    edge_stream: EdgeFrame = field(default_factory=EdgeFrame)


def pulse_samples_to_seconds(samples: int | None, divisor: int, clock_hz: int) -> float | None:
    return samples * divisor / clock_hz if samples is not None else None


def effective_virtual_hz(cycles: int, wall_elapsed: float) -> float:
    return cycles / wall_elapsed if cycles > 0 and wall_elapsed > 0.0 else 0.0


class SimulationEngine:
    """Own a model without owning a scheduler, GUI or preferences.

    Calls are synchronous. The engine owns closing the supplied model, and a
    host must keep all operations on the same thread. Power-off resets native
    capture/drivers and returns a blank frame; pause only suspends advancement.
    """

    def __init__(self, simulation: VerilatorSimulation, clock_hz: int, *,
                 observation_hz: int = 1_000_000,
                 led_sources: dict[int, tuple[str, int]] | None = None,
                 led_endpoints: tuple[str, ...] = (), led_active_low: tuple[bool, ...] = ()):
        if clock_hz <= 0 or observation_hz <= 0:
            raise ValueError(t("clock_hz and observation_hz must be positive."))
        self._simulation = simulation
        self._clock_hz = clock_hz
        self._observation_divisor = max(1, (clock_hz + observation_hz - 1) // observation_hz)
        simulation.set_observation_divisor(self._observation_divisor)
        self._cycle_remainder = 0.0
        self._performance_cycles = 0
        self._performance_wall_seconds = 0.0
        self._measured_virtual_hz = 0.0
        self._led_models = [LedModel() for _ in led_endpoints]
        self._led_active_low = led_active_low
        resolved = led_sources or {}
        self._led_sources = {index: resolved.get(index, (endpoint, 0))
                             for index, endpoint in enumerate(led_endpoints)}
        self._vga_bindings: tuple[VgaBinding, ...] = ()
        self._sink_id: int | None = None
        self._edge_channels: tuple[tuple[int, int], ...] = ()
        self._drive_channels: tuple[tuple[str, int, bool], ...] = ()
        self._drive_scheduler = TimedDriveScheduler(simulation)
        self._running = False
        self._powered_off = False
        self._closed = False

    @property
    def running(self) -> bool:
        return self._running

    @property
    def is_clocked(self) -> bool:
        return self._simulation.profile.clock_name is not None

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError(t("Simulation is closed."))

    def configure_vga_bindings(self, bindings) -> None:
        self._ensure_open()
        bindings = tuple(bindings or ())
        if bindings == self._vga_bindings and self._sink_id is not None:
            return
        if self._sink_id is not None:
            self._simulation.destroy_vga(self._sink_id)
            self._sink_id = None
        self._vga_bindings = bindings
        if len(bindings) > 1:
            raise ValueError(t("Only one VGA monitor is supported in this version."))
        if bindings:
            self._sink_id = self._simulation.configure_vga(bindings[0].timing, bindings[0].channels)

    def set_temporal_probes(self, probes) -> None:
        self._ensure_open()
        normalized = tuple(tuple(tuple(term) for term in probe) for probe in (probes or ()))
        self._simulation.set_temporal_probes(list(normalized))

    def configure_edge_channels(self, channels) -> None:
        self._ensure_open()
        try:
            normalized = tuple((int(output), int(bit)) for output, bit in (channels or ()))
            if normalized != self._edge_channels:
                self._simulation.configure_edge_channels(list(normalized))
                self._edge_channels = normalized
        except Exception:
            self._edge_channels = ()
            self._simulation.configure_edge_channels([])
            raise

    def configure_drive_channels(self, channels) -> None:
        self._ensure_open()
        try:
            normalized = tuple((str(name), int(bit), bool(idle)) for name, bit, idle in (channels or ()))
            if normalized != self._drive_channels:
                self._simulation.configure_drive_channels(list(normalized))
                self._drive_channels = normalized
                self._drive_scheduler.reset()
        except Exception:
            self._drive_channels = ()
            self._drive_scheduler.reset()
            self._simulation.configure_drive_channels([])
            raise

    def configure_spi_slaves(self, bindings) -> None:
        self._ensure_open()
        try:
            self._simulation.configure_spi_slaves(bindings or [])
        except Exception:
            try:
                self._simulation.configure_spi_slaves([])
            except Exception:
                pass
            raise

    def send_uart(self, channel: int, baud: int, text: str) -> int:
        """Schedule UTF-8 input; return byte count or raise on rejection."""
        self._ensure_open()
        if not self._running:
            raise ValueError(t("Start the simulation before sending UART text."))
        if not 0 <= channel < len(self._drive_channels):
            raise ValueError(t("UART TX is not connected to an FPGA input."))
        if baud <= 0 or baud > self._clock_hz // 2:
            raise ValueError(t("Baud rate is too high for the virtual clock."))
        data = text.encode("utf-8")
        if not data:
            return 0
        if len(data) > 512:
            raise ValueError(t("Send at most 512 UTF-8 bytes at once."))
        edges, end = uart_8n1_drive_events(data, 1, self._clock_hz, baud)
        self._drive_scheduler.enqueue(((channel, cycle - 1, level) for cycle, level in edges),
                                      end - 1, len(self._drive_channels))
        return len(data)

    def play(self) -> None:
        self._ensure_open()
        if not self._running:
            self._cycle_remainder = 0.0
            self._performance_cycles = 0
            self._performance_wall_seconds = 0.0
            self._measured_virtual_hz = 0.0
            self._powered_off = False
            self._running = True

    def pause(self) -> None:
        self._running = False

    def _reset_model(self) -> None:
        self._simulation.reset()
        self._simulation.streaming_reset()
        self._drive_scheduler.reset()

    def power_off(self) -> SimulationFrame:
        self._ensure_open()
        self.pause()
        self._powered_off = True
        self._reset_model()
        return SimulationFrame((0.0,) * len(self._led_models), {}, sinks={
            binding.peripheral_id: VgaSnapshot(pixels=b"", missing_required=binding.missing_required,
                                               bind_errors=binding.bind_errors)
            for binding in self._vga_bindings
        })

    def reset(self) -> SimulationFrame | None:
        self._ensure_open()
        was_running = self._running
        self.pause()
        self._reset_model()
        if was_running:
            self.play()
            return None
        return self.refresh()

    def set_input(self, name: str, value: int) -> SimulationFrame | None:
        self._ensure_open()
        self._simulation.set_input(name, value)
        return self.refresh()

    def refresh(self) -> SimulationFrame | None:
        """Refresh powered combinational outputs without advancing the clock."""
        self._ensure_open()
        if not self.is_clocked and not self._powered_off:
            return self._sample(0, 0.0)
        return None

    def _keep_sinks(self) -> dict[str, VgaSnapshot]:
        snapshots = {}
        for binding in self._vga_bindings:
            copied = None
            if self._sink_id is not None:
                copied = self._simulation.vga_copy_front(
                    self._sink_id, binding.timing.h_active, binding.timing.v_active)
            if copied is None:
                snapshots[binding.peripheral_id] = VgaSnapshot(
                    missing_required=binding.missing_required, bind_errors=binding.bind_errors)
                continue
            pixels, stats = copied
            snapshots[binding.peripheral_id] = VgaSnapshot(
                seq=stats.seq, width=binding.timing.h_active, height=binding.timing.v_active,
                pixels=pixels, stats=stats, missing_required=binding.missing_required,
                bind_errors=binding.bind_errors)
        return snapshots

    def advance(self, wall_elapsed: float) -> SimulationFrame | None:
        """Advance if running, capping catch-up at 100 ms per call.

        Speed uses uncapped wall time; protocols/persistence use virtual cycles.
        No elapsed time accumulates while paused.
        """
        self._ensure_open()
        if not self._running:
            return None
        if not math.isfinite(wall_elapsed) or wall_elapsed < 0:
            raise ValueError(t("Elapsed wall time must be finite and nonnegative."))
        try:
            exact_cycles = min(wall_elapsed, 0.100) * self._clock_hz + self._cycle_remainder
            cycles = int(exact_cycles)
            self._cycle_remainder = exact_cycles - cycles
            return self._sample(cycles, wall_elapsed)
        except Exception:
            self.pause()
            raise

    def _sample(self, cycles: int, wall_elapsed: float) -> SimulationFrame:
        self._simulation.ticks(cycles)
        windows = self._simulation.observed_windows(cycles)
        hits, samples, ends, edges = self._simulation.temporal_probe_window()
        pulses = self._simulation.temporal_pulse_window()
        edge_cycle, edge_events, dropped = self._simulation.edge_window()
        if dropped:
            edge_events = []
        virtual_elapsed = cycles / self._clock_hz
        leds = []
        for index, model in enumerate(self._led_models):
            port, bit = self._led_sources[index]
            signal = windows.get(f"{port}[{bit}]")
            if signal and index < len(self._led_active_low) and self._led_active_low[index]:
                signal = SignalWindow(not signal.start, not signal.end,
                                      signal.half_cycles - signal.high_halves,
                                      signal.half_cycles, signal.edges)
            leds.append(model.advance({"anode": signal}, virtual_elapsed) if signal else 0.0)
        outputs = {name: self._simulation.get_output(name) for name in self._simulation.profile.outputs}
        self._performance_cycles += cycles
        self._performance_wall_seconds += wall_elapsed
        if self._performance_wall_seconds >= 1.0:
            self._measured_virtual_hz = effective_virtual_hz(self._performance_cycles, self._performance_wall_seconds)
            self._performance_cycles = 0
            self._performance_wall_seconds = 0.0
        return SimulationFrame(
            tuple(leds), outputs, self._keep_sinks(), self._measured_virtual_hz, cycles,
            TemporalFrame(tuple(hits), samples, tuple(ends), tuple(edges), virtual_elapsed,
                          tuple(pulse_samples_to_seconds(value, self._observation_divisor, self._clock_hz)
                                for value in pulses)),
            EdgeFrame(edge_cycle, self._clock_hz, tuple(edge_events), dropped))

    def close(self) -> None:
        if not self._closed:
            self.pause()
            self._closed = True
            self._simulation.close()
