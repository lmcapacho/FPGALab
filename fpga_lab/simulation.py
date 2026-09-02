"""Minimal, typed, dependency-free ctypes binding for the C ABI."""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
from pathlib import Path

from .i18n import t
from .profile import BoardProfile
from .sink_bind import BoundBit, VgaTiming
from .temporal import SignalWindow


class SimVgaTiming(ctypes.Structure):
    """Matches ``SimVgaTiming`` in ``native/sim_streaming_abi.h`` (natural alignment)."""

    _fields_ = [
        ("h_active", ctypes.c_uint16),
        ("h_fp", ctypes.c_uint16),
        ("h_sync", ctypes.c_uint16),
        ("h_bp", ctypes.c_uint16),
        ("v_active", ctypes.c_uint16),
        ("v_fp", ctypes.c_uint16),
        ("v_sync", ctypes.c_uint16),
        ("v_bp", ctypes.c_uint16),
        ("hsync_active_low", ctypes.c_uint8),
        ("vsync_active_low", ctypes.c_uint8),
        ("color_depth", ctypes.c_uint8),
        ("skip_until_vsync", ctypes.c_uint8),
    ]


class SimVgaStats(ctypes.Structure):
    """Matches ``SimVgaStats`` in ``native/sim_streaming_abi.h`` (natural alignment)."""

    _fields_ = [
        ("frames_complete", ctypes.c_uint32),
        ("seq", ctypes.c_uint32),
        ("last_h_total", ctypes.c_uint32),
        ("last_v_total", ctypes.c_uint32),
        ("pixels_this_frame", ctypes.c_uint32),
        ("synced", ctypes.c_uint8),
        ("_pad", ctypes.c_uint8 * 3),
    ]


@dataclass(frozen=True)
class VgaStats:
    frames_complete: int
    seq: int
    last_h_total: int
    last_v_total: int
    pixels_this_frame: int
    synced: bool


class VerilatorSimulation:
    """One Verilator model instance, used from a single thread.

    The library uses a global model. ticks(), getters, and sim_vga_copy_front
    must run on that thread (SimulationWorker). The UI thread owns copies of
    pixel bytes, never C++ framebuffer pointers.
    """

    def __init__(self, library: str | Path, profile: BoardProfile):
        self.profile = profile
        library_path = Path(library).resolve()
        if not library_path.is_file():
            raise FileNotFoundError(library_path)
        self._lib = ctypes.CDLL(str(library_path))
        self._configure_api()
        self._lib.init_sim()

    def _function(self, name: str, restype, argtypes=()):
        function = getattr(self._lib, name)
        function.restype = restype
        function.argtypes = list(argtypes)
        return function

    def _configure_api(self) -> None:
        self._init = self._function("init_sim", None)
        self._reset = self._function("reset_sim", None)
        self._close = self._function("close_sim", None)
        self._eval = self._function("eval_sim", None)
        self._step = self._function("step_clock", None)
        self._run_cycles = self._function("run_cycles", None, (ctypes.c_uint64,))
        self._observed_count = self._function("sim_observed_count", ctypes.c_uint32)
        self._observed_samples = self._function("sim_observed_samples", ctypes.c_uint64)
        self._set_observation_divisor = self._function("sim_set_observation_divisor", None, (ctypes.c_uint64,))
        self._observed_start = self._function("sim_observed_start", ctypes.c_uint8, (ctypes.c_uint32,))
        self._observed_end = self._function("sim_observed_end", ctypes.c_uint8, (ctypes.c_uint32,))
        self._observed_high_halves = self._function("sim_observed_high_halves", ctypes.c_uint64, (ctypes.c_uint32,))
        self._observed_edges = self._function("sim_observed_edges", ctypes.c_uint64, (ctypes.c_uint32,))
        self._set_clk = self._function("sim_set_clk", None, (ctypes.c_uint8,))
        self._get_clk = self._function("sim_get_clk", ctypes.c_uint8)
        self._setters = {
            name: self._function(f"sim_set_{name}", None, (ctypes.c_uint64,))
            for name in self.profile.inputs if name != self.profile.clock_name
        }
        self._getters = {
            name: self._function(f"sim_get_{name}", ctypes.c_uint64)
            for name in self.profile.outputs
        }
        self._read_output = self._function("sim_read_output", ctypes.c_uint64, (ctypes.c_uint32,))
        self._vga_create = self._function("sim_vga_create", ctypes.c_int, (ctypes.POINTER(ctypes.c_uint32),))
        self._vga_destroy = self._function("sim_vga_destroy", None, (ctypes.c_uint32,))
        self._vga_configure = self._function("sim_vga_configure", ctypes.c_int, (ctypes.c_uint32, ctypes.POINTER(SimVgaTiming)))
        self._vga_bind_bit = self._function(
            "sim_vga_bind_bit", ctypes.c_int, (ctypes.c_uint32, ctypes.c_uint32, ctypes.c_int32, ctypes.c_uint8)
        )
        self._vga_enable = self._function("sim_vga_enable", None, (ctypes.c_uint32, ctypes.c_uint8))
        self._vga_seq = self._function("sim_vga_seq", ctypes.c_uint32, (ctypes.c_uint32,))
        self._vga_copy_front = self._function(
            "sim_vga_copy_front",
            ctypes.c_int,
            (ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32), ctypes.c_uint32, ctypes.POINTER(SimVgaStats)),
        )
        self._vga_stats = self._function("sim_vga_stats", None, (ctypes.c_uint32, ctypes.POINTER(SimVgaStats)))
        self._streaming_reset = self._function("sim_streaming_reset", None)
        self._streaming_close = self._function("sim_streaming_close", None)
        self._streaming_on_posedge = self._function("sim_streaming_on_posedge", None)

    def tick(self) -> None:
        """One full period: rising edge/evaluation followed by falling edge/evaluation."""
        self._step()

    def ticks(self, count: int) -> None:
        if count < 0:
            raise ValueError(t("Cycle count cannot be negative."))
        self._run_cycles(count)

    def reset(self) -> None:
        """Electrically reset the model while keeping its library and profile."""
        self._reset()

    def set_observation_divisor(self, cycles: int) -> None:
        """Set output observation frequency in virtual cycles (minimum one)."""
        if cycles < 1:
            raise ValueError("Observation divisor must be positive.")
        self._set_observation_divisor(cycles)

    def observed_windows(self, cycles: int) -> dict[str, SignalWindow]:
        """Metrics from the last ``ticks`` call; keys such as ``gpio_out[3]``."""
        if cycles < 0:
            raise ValueError(t("Cycle count cannot be negative."))
        observed_bits = self.profile.observed_bits
        if self._observed_count() != len(observed_bits):
            raise RuntimeError(t("The profile does not match the compiled Verilator library."))
        half_cycles = int(self._observed_samples())
        return {
            f"{name}[{bit}]": SignalWindow(
                start=bool(self._observed_start(index)),
                end=bool(self._observed_end(index)),
                high_halves=int(self._observed_high_halves(index)),
                half_cycles=half_cycles,
                edges=int(self._observed_edges(index)),
            )
            for index, (name, bit) in enumerate(observed_bits)
        }

    @property
    def clk(self) -> bool:
        return bool(self._get_clk())

    @clk.setter
    def clk(self, value: bool) -> None:
        self._set_clk(bool(value))
        self._eval()

    def set_input(self, name: str, value: int | bool) -> None:
        if name == self.profile.clock_name:
            self.clk = bool(value)
            return
        try:
            width = self.profile.inputs[name]
        except KeyError as exc:
            raise KeyError(t("Undeclared input: {name}", name=name)) from exc
        if not 0 <= int(value) < (1 << width):
            raise ValueError(t("{name} accepts a {width}-bit value.", name=name, width=width))
        self._setters[name](int(value))
        self._eval()

    def get_output(self, name: str) -> int:
        try:
            return int(self._getters[name]())
        except KeyError as exc:
            raise KeyError(t("Undeclared output: {name}", name=name)) from exc

    def read_output(self, index: int) -> int:
        return int(self._read_output(index))

    def configure_vga(self, timing: VgaTiming, channels: dict[int, BoundBit]) -> int:
        """Create, configure, bind, and enable one VGA sink. Worker thread only."""
        sink_id = ctypes.c_uint32()
        if self._vga_create(ctypes.byref(sink_id)) != 0:
            raise RuntimeError(t("Only one VGA monitor is supported in this version."))
        c_timing = SimVgaTiming(
            timing.h_active, timing.h_fp, timing.h_sync, timing.h_bp,
            timing.v_active, timing.v_fp, timing.v_sync, timing.v_bp,
            timing.hsync_active_low, timing.vsync_active_low,
            timing.color_depth, timing.skip_until_vsync,
        )
        if self._vga_configure(sink_id, ctypes.byref(c_timing)) != 0:
            self._vga_destroy(sink_id)
            raise RuntimeError(t("VGA monitor could not allocate a framebuffer."))
        for channel, bound in channels.items():
            self._vga_bind_bit(sink_id.value, channel, bound.port_index, bound.bit)
        self._vga_enable(sink_id, 1)
        return int(sink_id.value)

    def destroy_vga(self, sink_id: int) -> None:
        self._vga_destroy(sink_id)

    def vga_seq(self, sink_id: int = 0) -> int:
        return int(self._vga_seq(sink_id))

    def vga_copy_front(self, sink_id: int, width: int, height: int) -> tuple[bytes, VgaStats] | None:
        n = width * height
        buf = (ctypes.c_uint32 * n)()
        stats = SimVgaStats()
        if self._vga_copy_front(sink_id, buf, n * 4, ctypes.byref(stats)) != 0:
            return None
        return bytes(buf), VgaStats(
            frames_complete=int(stats.frames_complete),
            seq=int(stats.seq),
            last_h_total=int(stats.last_h_total),
            last_v_total=int(stats.last_v_total),
            pixels_this_frame=int(stats.pixels_this_frame),
            synced=bool(stats.synced),
        )

    def vga_stats(self, sink_id: int = 0) -> VgaStats:
        stats = SimVgaStats()
        self._vga_stats(sink_id, ctypes.byref(stats))
        return VgaStats(
            frames_complete=int(stats.frames_complete),
            seq=int(stats.seq),
            last_h_total=int(stats.last_h_total),
            last_v_total=int(stats.last_v_total),
            pixels_this_frame=int(stats.pixels_this_frame),
            synced=bool(stats.synced),
        )

    def streaming_reset(self) -> None:
        self._streaming_reset()

    def read_leds(self) -> list[bool]:
        """UI convention: LED0 is the first item in the returned list."""
        return [bool(self.get_output(f"LED{index}")) if f"LED{index}" in self._getters else False
                for index in range(8)]

    def close(self) -> None:
        if getattr(self, "_lib", None) is not None:
            self._close()
            self._lib = None

    def __enter__(self) -> "VerilatorSimulation":
        return self

    def __exit__(self, *_unused) -> None:
        self.close()
