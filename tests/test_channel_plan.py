"""Headless channel planning, with synthetic connections and explicit catalogs."""

import json
from pathlib import Path

from fpga_lab.peripherals.catalog import load_catalog
from fpga_lab.peripherals.channel_plan import ChannelPlan, build_channel_plan
from fpga_lab.peripherals.manifest import parse_manifest
from fpga_lab.profile import BoardProfile
from fpga_lab.wiring import PeripheralInstance, ResolvedWire, VirtualLabProject


def example_spec(identifier):
    root = Path(__file__).parents[1] / "examples/peripherals" / identifier
    return parse_manifest(json.loads((root / "manifest.json").read_text()), resource_root=root)


def wires_for(identifier, **nets):
    return tuple(ResolvedWire(identifier, terminal, "synthetic", net) for terminal, net in nets.items())


def test_serial_channel_indices_follow_project_manifest_and_profile_order():
    catalog = {name: example_spec(name) for name in ("uart_terminal", "spi_monitor")}
    project = VirtualLabProject((
        PeripheralInstance("uart", "uart_terminal", {}, {}),
        PeripheralInstance("spi", "spi_monitor", {}, {"mode": "3", "bit_order": "lsb",
                                                       "cs_polarity": "high", "response": "3C"}),
        PeripheralInstance("unavailable", "future_type", {}, {}),
    ))
    wires = (wires_for("uart", rx="bus[3]", tx="inputs[2]")
             + wires_for("spi", sck="sck", mosi="bus[0]", cs="select", miso="inputs[1]"))
    profile = BoardProfile("test", {"clk": 1, "inputs": 4},
                           {"select": 1, "bus": 4, "sck": 1})
    plan = build_channel_plan(project, wires, profile, catalog=catalog)
    assert plan.edge_bindings == (("uart", "rx", 1, 3), ("spi", "sck", 2, 0),
                                  ("spi", "mosi", 1, 0), ("spi", "cs", 0, 0))
    assert plan.edge_channels == ((1, 3), (2, 0), (1, 0), (0, 0))
    assert plan.drive_bindings == (("uart", "tx", "inputs", 2, True),
                                   ("spi", "miso", "inputs", 1, False))
    assert plan.drive_channels == (("inputs", 2, True), ("inputs", 1, False))
    assert plan.spi_slaves == ((2, 0, 0, 0, 1, 3, True, False, 0x3C),)
    assert plan.spi_response_peripherals == frozenset({"spi"})
    assert plan.warnings == ()
    assert build_channel_plan(project, wires, profile, catalog=catalog) == plan


def test_unmapped_invalid_clock_and_optional_channels_do_not_allocate_slots():
    catalog = {"spi_monitor": example_spec("spi_monitor")}
    project = VirtualLabProject((PeripheralInstance("spi", "spi_monitor", {}, {}),))
    profile = BoardProfile("test", {"clk": 1, "input": 1}, {"output": 1})
    for net in (None, "missing", "output[1]", "input", "output[bad]"):
        plan = build_channel_plan(project, wires_for("spi", sck=net, miso="clk"),
                                  profile, catalog=catalog)
        assert plan == ChannelPlan()
    plan = build_channel_plan(project, wires_for("spi", sck="output", miso="input"),
                              profile, catalog=catalog)
    assert plan.edge_channels == ((0, 0),)
    assert plan.drive_channels == (("input", 0, False),)
    assert plan.spi_slaves == ()  # Missing CS, not a usable responder.
    invalid = VirtualLabProject((PeripheralInstance("spi", "spi_monitor", {}, {"response": "invalid"}),))
    plan = build_channel_plan(invalid, wires_for("spi", sck="output", cs="output", miso="input"),
                              profile, catalog=catalog)
    assert plan.spi_slaves == () and not plan.spi_response_peripherals
    assert len(plan.warnings) == 1 and "hexadecimal" in plan.warnings[0]
    assert invalid.peripherals[0].properties == {"response": "invalid"}


def test_temporal_polarity_common_gating_and_sampled_fallback_suppression():
    catalog = {key: load_catalog()[key] for key in ("led", "seven_segment")}
    profile = BoardProfile("test", {}, {"segments": 7, "enable": 1}, clock_name=None)
    wires = wires_for("display", a="segments[0]", b="segments[1]", common="enable")
    for polarity, common, expected in (
        ("cathode", "GND", ((0, 0, True),)),
        ("anode", "VCC", ((0, 0, False),)),
        ("cathode", "header", ((1, 0, False), (0, 0, True))),
        ("anode", "header", ((1, 0, True), (0, 0, False))),
    ):
        project = VirtualLabProject((PeripheralInstance("display", "seven_segment",
                                                       {"common": common}, {"common": polarity}),))
        plan = build_channel_plan(project, wires, profile, catalog=catalog)
        assert plan.temporal_probes[0] == expected
        assert plan.temporal_bindings == (("display", "a"), ("display", "b"))
        assert len(plan.temporal_terminals) == 7
    project = VirtualLabProject((PeripheralInstance("display", "seven_segment", {"common": "GND"},
                                                   {"common": "anode"}),
                                 PeripheralInstance("lamp", "led", {}, {})))
    plan = build_channel_plan(project, wires + wires_for("lamp", anode="enable"), profile, catalog=catalog)
    assert plan.temporal_probes == (((1, 0, True),),)
    assert plan.temporal_bindings == (("lamp", "anode"),)
    assert ("display", "a") in plan.temporal_terminals
    assert ("lamp", "anode") in plan.temporal_terminals
