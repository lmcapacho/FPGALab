"""Bind streaming-sink terminals to profile output port index + bit."""

from __future__ import annotations

from dataclasses import dataclass

from .signals import signal_reference
from .peripherals.catalog import load_catalog
from .profile import BoardProfile
from .wiring import PeripheralInstance, ResolvedWire, VirtualLabProject

SIM_VGA_CHANNEL_HSYNC = 0
SIM_VGA_CHANNEL_VSYNC = 1
SIM_VGA_CHANNEL_R0 = 2
SIM_VGA_CHANNEL_G0 = 6
SIM_VGA_CHANNEL_B0 = 10

VGA_CHANNELS = {
    "hsync": SIM_VGA_CHANNEL_HSYNC,
    "vsync": SIM_VGA_CHANNEL_VSYNC,
    "r0": 2, "r1": 3, "r2": 4, "r3": 5,
    "g0": 6, "g1": 7, "g2": 8, "g3": 9,
    "b0": 10, "b1": 11, "b2": 12, "b3": 13,
}


@dataclass(frozen=True)
class BoundBit:
    port_index: int
    bit: int


@dataclass(frozen=True)
class BindResult:
    bound: BoundBit
    error: str | None


@dataclass(frozen=True)
class VgaTiming:
    h_active: int = 640
    h_fp: int = 16
    h_sync: int = 96
    h_bp: int = 48
    v_active: int = 480
    v_fp: int = 10
    v_sync: int = 2
    v_bp: int = 33
    hsync_active_low: int = 1
    vsync_active_low: int = 1
    color_depth: int = 1
    skip_until_vsync: int = 1


@dataclass(frozen=True)
class VgaBinding:
    peripheral_id: str
    timing: VgaTiming
    channels: dict[int, BoundBit]
    missing_required: tuple[str, ...]
    bind_errors: tuple[str, ...]


def bind_terminal(wire: ResolvedWire | None, profile: BoardProfile) -> BindResult:
    if wire is None or not wire.hdl_net:
        return BindResult(BoundBit(-1, 0), None)
    parsed = signal_reference(wire.hdl_net, profile.outputs)
    if parsed is None:
        name = wire.hdl_net.split("[", 1)[0]
        if name in profile.inputs:
            return BindResult(
                BoundBit(-1, 0),
                f"{wire.terminal}: HDL net {wire.hdl_net!r} is inputs, not an output. "
                "VGA capture cannot read inout/clock/input pins.",
            )
        if name not in profile.outputs:
            return BindResult(
                BoundBit(-1, 0),
                f"{wire.terminal}: HDL net {wire.hdl_net!r} is undeclared, not an output. "
                "VGA capture cannot read inout/clock/input pins.",
            )
        return BindResult(
            BoundBit(-1, 0),
            f"{wire.terminal}: bit is outside {name}[{profile.outputs[name] - 1}:0].",
        )
    name, bit = parsed
    return BindResult(BoundBit(tuple(profile.outputs).index(name), bit), None)


def bits_per_channel(spec, properties: dict) -> int:
    raw = properties.get("color_depth")
    if raw is not None:
        try:
            value = int(str(raw))
        except (TypeError, ValueError):
            value = 0
        if value in {1, 2, 4}:
            return value
    return spec.color_depth or 1


def timing_from_properties(properties: dict, spec=None) -> VgaTiming:
    return VgaTiming(
        color_depth=bits_per_channel(spec, properties) if spec is not None else 1,
        hsync_active_low=0 if properties.get("hsync_polarity") == "active_high" else 1,
        vsync_active_low=0 if properties.get("vsync_polarity") == "active_high" else 1,
        skip_until_vsync=0 if properties.get("skip_until_vsync") is False else 1,
    )


def collect_vga_bindings(
    project: VirtualLabProject,
    wires: tuple[ResolvedWire, ...],
    profile: BoardProfile,
) -> tuple[VgaBinding, ...]:
    catalog = load_catalog()
    by_id: dict[str, dict[str, ResolvedWire]] = {}
    for wire in wires:
        by_id.setdefault(wire.peripheral_id, {})[wire.terminal] = wire
    bindings: list[VgaBinding] = []
    for peripheral in project.peripherals:
        spec = catalog.get(peripheral.kind)
        if spec is None or spec.sink_kind != "vga":
            continue
        bindings.append(_bind_monitor(peripheral, by_id.get(peripheral.peripheral_id, {}), profile, spec))
    return tuple(bindings)


def _bind_monitor(peripheral: PeripheralInstance, wires: dict[str, ResolvedWire], profile: BoardProfile, spec) -> VgaBinding:
    required = spec.required_terminals(peripheral.properties)
    missing: list[str] = []
    errors: list[str] = []
    channels: dict[int, BoundBit] = {}
    for terminal, channel in VGA_CHANNELS.items():
        wire = wires.get(terminal)
        if terminal in required and (wire is None or not wire.hdl_net):
            if wire is None or not peripheral.connections.get(terminal):
                missing.append(terminal)
            else:
                missing.append(f"{terminal} not mapped by PCF")
        result = bind_terminal(wire, profile)
        if result.error:
            errors.append(result.error)
        channels[channel] = result.bound
    return VgaBinding(
        peripheral.peripheral_id,
        timing_from_properties(peripheral.properties, spec),
        channels,
        tuple(missing),
        tuple(errors),
    )
