"""Framework-free preparation, compilation and ownership of one active session.

Operations are synchronous. Hosts schedule build work and serialize model access;
this service does not own a GUI, thread pool, preferences or network transport.
"""

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Callable

from .board import DEFAULT_BOARD_ID, BoardDefinition, bundled_board_definition
from .board_catalog import BoardCatalog
from .build_cache import CachedBuild, VerilatorBuildCache
from .compiler import BuildCancelled
from .constraints import parse_constraints_file
from .ice_project import IcestudioProject
from .messages import t
from .profile import BoardProfile
from .profile_policy import apply_led_observed
from .project_pins import ProjectPinMap
from .signals import signal_reference
from .simulation import VerilatorSimulation
from .simulation_engine import SimulationEngine
from .verilog_interface import VerilogInterface
from .wiring import ResolvedWire, VirtualLabProject, validate_lab_document


def project_clock_port(project: IcestudioProject, interface: VerilogInterface,
                       board_id: str = DEFAULT_BOARD_ID) -> str | None:
    if project.pcf is None:
        return None
    board = BoardDefinition.load(bundled_board_definition(board_id))
    pin_map = ProjectPinMap.from_constraints(board, project.pcf)
    inputs = {port.name: port.width for port in interface.ports if port.direction in {"input", "inout"}}
    reference = signal_reference(pin_map.net_for(board.clock_endpoint), inputs) if board.clock_endpoint else None
    return reference[0] if reference is not None and reference[1] == 0 and inputs[reference[0]] == 1 else None


def board_sources(project: IcestudioProject, profile: BoardProfile,
                  board_id: str = DEFAULT_BOARD_ID) -> tuple[dict[int, tuple[str, int]], dict[str, tuple[str, int]]]:
    if project.pcf is None:
        return {}, {}
    board = BoardDefinition.load(bundled_board_definition(board_id))
    pin_map = ProjectPinMap.from_constraints(board, project.pcf)
    leds = {index: reference for index, endpoint in enumerate(board.led_endpoints)
            if (reference := signal_reference(pin_map.net_for(endpoint), profile.outputs)) is not None}
    inputs = {endpoint: reference for endpoint in board.input_endpoints
              if (reference := signal_reference(pin_map.net_for(endpoint), profile.inputs)) is not None}
    return leds, inputs


@dataclass(frozen=True)
class PreparedSession:
    """Preparation result; source files and the Lab are never rewritten."""

    project: IcestudioProject
    profile: BoardProfile
    module_name: str
    led_sources: dict[int, tuple[str, int]]
    input_sources: dict[str, tuple[str, int]]
    board_id: str = DEFAULT_BOARD_ID
    lab_file: Path | None = None
    lab: VirtualLabProject | None = None
    wires: tuple[ResolvedWire, ...] = ()
    warnings: tuple[str, ...] = ()
    clock_hz: int | None = None
    lab_document: dict[str, object] | None = None


@dataclass(frozen=True)
class SimulationSession:
    """Owned native model/engine and the design they were prepared from."""

    prepared: PreparedSession
    artifact: CachedBuild
    simulation: VerilatorSimulation
    engine: SimulationEngine

    def close(self) -> None:
        self.engine.close()

    def __enter__(self) -> "SimulationSession":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


class SessionService:
    """One active model per service; open only after its old owner has stopped.

    Separate service instances must not open the same native library concurrently:
    its C ABI has process-global state. This is not a multi-client isolation layer.
    """

    def __init__(self, cache_dir: str | Path | None = None, *,
                 cache: VerilatorBuildCache | None = None):
        self._cache = cache if cache is not None else VerilatorBuildCache(cache_dir)
        self._current: SimulationSession | None = None

    @property
    def current(self) -> SimulationSession | None:
        return self._current

    def prepare(self, ice_file: str | Path, *, lab_file: str | Path | None = None,
                board_id: str | None = None, profile: BoardProfile | None = None,
                clock_hz: int | None = None) -> PreparedSession:
        raw = {}
        lab_path = Path(lab_file).expanduser().resolve() if lab_file is not None else None
        if lab_path is not None:
            raw = json.loads(lab_path.read_text(encoding="utf-8"))
            validate_lab_document(raw)
        metadata = raw.get("metadata", {})
        package = BoardCatalog().resolve(board_id or metadata.get("board_id") or DEFAULT_BOARD_ID)
        override = metadata.get("virtual_clock_hz")
        resolved_clock = clock_hz if clock_hz is not None else (
            override if override is not None else package.definition.clock_hz)
        self._validate_rates(resolved_clock, 1_000_000)
        project = IcestudioProject.discover(ice_file)
        interface = VerilogInterface.discover(project.main_v)
        selected_profile = profile or interface.profile(
            board_name=package.definition.label,
            clock_port=project_clock_port(project, interface, package.board_id))
        selected_profile.validate()
        leds, inputs = board_sources(project, selected_profile, package.board_id)
        if profile is None:
            selected_profile = apply_led_observed(selected_profile, leds)
        lab = VirtualLabProject.from_raw(raw)
        constraints = parse_constraints_file(project.pcf) if project.pcf else []
        wires, warnings = lab.resolve_compatible(package.definition, constraints)
        return PreparedSession(project, selected_profile, interface.module_name, leds, inputs,
                               package.board_id, lab_path, lab, wires, warnings, resolved_clock, raw)

    def build(self, prepared: PreparedSession, *, optimization_mode: str = "automatic",
              verilator: str | None = None,
              cancel_requested: Callable[[], bool] | None = None) -> CachedBuild:
        if cancel_requested and cancel_requested():
            raise BuildCancelled("Build cancelled")
        artifact = self._cache.build_or_reuse(
            prepared.project, prepared.profile, top_module=prepared.module_name,
            optimization_mode=optimization_mode, verilator=verilator,
            cancel_requested=cancel_requested)
        if cancel_requested and cancel_requested():
            raise BuildCancelled("Build cancelled")
        return artifact

    @staticmethod
    def _validate_rates(clock_hz: int, observation_hz: int) -> None:
        if any(not isinstance(value, int) or isinstance(value, bool) or value <= 0
               for value in (clock_hz, observation_hz)):
            raise ValueError(t("clock_hz and observation_hz must be positive."))

    def open(self, prepared: PreparedSession, artifact: CachedBuild, *,
             clock_hz: int | None = None, observation_hz: int = 1_000_000) -> SimulationSession:
        board = BoardCatalog().get(prepared.board_id).definition
        clock = clock_hz if clock_hz is not None else prepared.clock_hz
        if clock is None:
            clock = board.clock_hz
        self._validate_rates(clock, observation_hz)
        # Native init_sim must never run while the previous model is still live.
        self.close()
        simulation = VerilatorSimulation(artifact.library, prepared.profile)
        try:
            engine = SimulationEngine(
                simulation, clock, observation_hz=observation_hz,
                led_sources=prepared.led_sources, led_endpoints=board.led_endpoints,
                led_active_low=tuple(board.pin(endpoint).active_low for endpoint in board.led_endpoints))
            # Establish inactive levels of integrated controls, including
            # active-low buttons, before the first model frame.
            idle_inputs = {}
            for endpoint, (port, bit) in prepared.input_sources.items():
                idle_inputs.setdefault(port, 0)
                if board.pin(endpoint).active_low:
                    idle_inputs[port] |= 1 << bit
            for port, value in idle_inputs.items():
                simulation.set_input(port, value)
        except Exception:
            simulation.close()
            raise
        self._current = SimulationSession(prepared, artifact, simulation, engine)
        return self._current

    def close(self) -> None:
        if self._current is not None:
            self._current.close()
            self._current = None
