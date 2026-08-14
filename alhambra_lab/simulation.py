"""Binding ctypes mínimo, tipado y sin dependencias externas para la ABI C."""

from __future__ import annotations

import ctypes
from pathlib import Path

from .profile import BoardProfile


class VerilatorSimulation:
    """Instancia de un único modelo Verilator, utilizada desde un solo hilo.

    La biblioteca usa un modelo global deliberadamente: cada DLL/SO representa
    una FPGA virtual. Si se requieren varias placas simultáneas, compile una
    copia de la biblioteca por placa o evolucione la ABI a manejadores opacos.
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
        self._set_clk = self._function("sim_set_clk", None, (ctypes.c_uint8,))
        self._get_clk = self._function("sim_get_clk", ctypes.c_uint8)
        self._setters = {
            name: self._function(f"sim_set_{name}", None, (ctypes.c_uint64,))
            for name in self.profile.inputs if name != "clk"
        }
        self._getters = {
            name: self._function(f"sim_get_{name}", ctypes.c_uint64)
            for name in self.profile.outputs
        }

    def tick(self) -> None:
        """Un periodo completo: flanco ascendente/evaluación y descendente/evaluación."""
        self._step()

    def ticks(self, count: int) -> None:
        for _ in range(count):
            self._step()

    @property
    def clk(self) -> bool:
        return bool(self._get_clk())

    @clk.setter
    def clk(self, value: bool) -> None:
        self._set_clk(bool(value))
        self._eval()

    def set_input(self, name: str, value: int | bool) -> None:
        if name == "clk":
            self.clk = bool(value)
            return
        try:
            width = self.profile.inputs[name]
        except KeyError as exc:
            raise KeyError(f"Entrada no declarada: {name}") from exc
        if not 0 <= int(value) < (1 << width):
            raise ValueError(f"{name} admite un valor de {width} bits.")
        self._setters[name](int(value))
        self._eval()

    def get_output(self, name: str) -> int:
        try:
            return int(self._getters[name]())
        except KeyError as exc:
            raise KeyError(f"Salida no declarada: {name}") from exc

    def read_leds(self) -> list[bool]:
        """Convención UI: LED0 es el primer elemento de la lista."""
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
