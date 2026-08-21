"""Minimal, typed, dependency-free ctypes binding for the C ABI."""

from __future__ import annotations

import ctypes
from pathlib import Path

from .i18n import t
from .profile import BoardProfile
from .temporal import SignalWindow


class VerilatorSimulation:
    """One Verilator model instance, used from a single thread.

    The library deliberately uses a global model: each DLL/SO represents one
    virtual FPGA. Multiple simultaneous boards require one library per board
    or a future ABI based on opaque handles.
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

    def tick(self) -> None:
        """One full period: rising edge/evaluation followed by falling edge/evaluation."""
        self._step()

    def ticks(self, count: int) -> None:
        if count < 0:
            raise ValueError(t("Cycle count cannot be negative.", "La cantidad de ciclos no puede ser negativa."))
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
            raise ValueError(t("Cycle count cannot be negative.", "La cantidad de ciclos no puede ser negativa."))
        observed_bits = self.profile.observed_bits
        if self._observed_count() != len(observed_bits):
            raise RuntimeError(t("The profile does not match the compiled Verilator library.", "El perfil no coincide con la biblioteca Verilator compilada."))
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
            raise KeyError(t("Undeclared input: {name}", "Entrada no declarada: {name}", name=name)) from exc
        if not 0 <= int(value) < (1 << width):
            raise ValueError(t("{name} accepts a {width}-bit value.", "{name} admite un valor de {width} bits.", name=name, width=width))
        self._setters[name](int(value))
        self._eval()

    def get_output(self, name: str) -> int:
        try:
            return int(self._getters[name]())
        except KeyError as exc:
            raise KeyError(t("Undeclared output: {name}", "Salida no declarada: {name}", name=name)) from exc

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
