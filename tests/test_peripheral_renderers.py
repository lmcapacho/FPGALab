"""Generic renderer behavior and external no-code examples."""

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtWidgets import QApplication

from fpga_lab.peripherals.catalog import discover_catalog, icon_path_for, load_catalog
from fpga_lab.peripherals.manifest import parse_manifest
from fpga_lab.peripherals.renderers.bcd_display import (
    active_bcd_segments,
    bcd_enable_active,
    bcd_segments,
)
from fpga_lab.peripherals.renderers.dip_switch import DipSwitchRenderer
from fpga_lab.peripherals.renderers.toggle_switch import ToggleSwitchRenderer
from fpga_lab.peripherals.renderers import renderer_for
from fpga_lab.wiring import PeripheralInstance


_APPLICATION = QApplication.instance() or QApplication([])


def test_external_pwm_meter_uses_temporal_output_without_python_plugin():
    root = Path(__file__).parents[1] / "examples" / "peripherals" / "pwm_meter"
    spec = parse_manifest(json.loads((root / "manifest.json").read_text(encoding="utf-8")), resource_root=root)
    assert spec.simulation_class == "gpio_temporal"
    assert spec.temporal == {"mode": "per_terminal"}
    assert spec.visual["terminal"] == "signal"
    renderer = renderer_for(spec.visual["renderer"], spec.visual, spec.resource_root)
    image = QImage(132, 94, QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    renderer.paint(painter, None, PeripheralInstance("pwm_meter_1", "pwm_meter", {}, {}), {
        "powered": True,
        "temporal": {"signal": {"duty_cycle": 0.25, "edge_rate_hz": 1000.0}},
    })
    painter.end()
    assert image.pixelColor(30, 49) != image.pixelColor(80, 49)


def test_bcd_display_declares_four_bits_and_shows_hexadecimal_codes():
    display = load_catalog()["bcd_display"]

    assert display.required_terminals() == ("A", "B", "C", "D")
    assert display.visual["renderer"] == "bcd_display"
    assert display.visual["chrome"] == "compact"
    assert display.terminal_map()["enable"].required is False
    assert bcd_segments(0) == frozenset("abcdef")
    assert bcd_segments(8) == frozenset("abcdefg")
    assert bcd_segments(9) == frozenset("abcdfg")
    assert bcd_segments(10) == frozenset("abcefg")
    assert bcd_segments(11) == frozenset("cdefg")
    assert bcd_segments(15) == frozenset("aefg")
    zero = {terminal: False for terminal in ("A", "B", "C", "D")}
    assert active_bcd_segments({}, True) == frozenset()
    assert active_bcd_segments(zero, False) == frozenset()
    assert active_bcd_segments(zero, True) == frozenset("abcdef")
    assert bcd_enable_active({}, None)
    assert bcd_enable_active({"enable": True}, "D0")
    assert not bcd_enable_active({"enable": False}, "D0")
    assert active_bcd_segments(zero, True, enable_endpoint="D0") == frozenset()
    assert active_bcd_segments({**zero, "enable": True}, True, enable_endpoint="D0") == frozenset("abcdef")


def test_four_position_dip_switch_toggles_and_resynchronizes_each_input():
    spec = load_catalog()["dip_switch"]
    renderer = DipSwitchRenderer()
    peripheral = PeripheralInstance("dip_switch_1", "dip_switch", {}, {})
    changes: list[tuple[str, str, int]] = []
    changed = lambda identifier, terminal, value: changes.append((identifier, terminal, value))

    renderer.mouse_press(peripheral, QPointF(39, 34), changed)
    renderer.mouse_press(peripheral, QPointF(91, 34), changed)
    renderer.sync_inputs(peripheral, changed)

    assert spec.required_terminals() == ("SW1", "SW2", "SW3", "SW4")
    assert renderer.values() == (True, False, True, False)
    assert changes[-4:] == [
        ("dip_switch_1", "SW1", 1),
        ("dip_switch_1", "SW2", 0),
        ("dip_switch_1", "SW3", 1),
        ("dip_switch_1", "SW4", 0),
    ]


def test_toggle_switch_latches_and_resynchronizes_its_input():
    spec = load_catalog()["toggle_switch"]
    renderer = ToggleSwitchRenderer()
    peripheral = PeripheralInstance("switch_1", "toggle_switch", {}, {})
    changes: list[tuple[str, str, int]] = []
    changed = lambda identifier, terminal, value: changes.append((identifier, terminal, value))

    renderer.mouse_press(peripheral, QPointF(48, 25), changed)
    renderer.sync_inputs(peripheral, changed)
    renderer.mouse_press(peripheral, QPointF(48, 25), changed)

    assert spec.required_terminals() == ("signal",)
    assert changes == [
        ("switch_1", "signal", 1),
        ("switch_1", "signal", 1),
        ("switch_1", "signal", 0),
    ]


def test_external_led_bar_loads_and_renders_without_a_peripheral_registry_entry(tmp_path, monkeypatch):
    source = Path(__file__).parents[1] / "examples" / "peripherals" / "led_bar"
    external_root = tmp_path / "peripherals"
    installed = external_root / "led_bar"
    installed.mkdir(parents=True)
    for name in ("manifest.json", "icon.svg"):
        (installed / name).write_bytes((source / name).read_bytes())

    catalog = discover_catalog((external_root,))
    spec = catalog["led_bar"]
    assert spec.simulation_class == "gpio_temporal"
    assert spec.visual["renderer"] == "led_array"
    assert len(spec.required_terminals()) == 8

    monkeypatch.setenv("FPGALAB_PERIPHERALS_DIR", str(external_root))
    load_catalog.cache_clear()
    try:
        loaded = load_catalog()["led_bar"]
        assert icon_path_for(loaded) == installed / "icon.svg"
        renderer = renderer_for(loaded.visual["renderer"], loaded.visual)
        assert renderer.size(PeripheralInstance("bar_1", "led_bar", {}, {})) == (190, 92)
        image = QImage(190, 92, QImage.Format.Format_ARGB32)
        image.fill(0)
        painter = QPainter(image)
        renderer.paint(
            painter,
            None,
            PeripheralInstance("bar_1", "led_bar", {}, {"color": "#ef4444"}),
            {"brightness": {"LED0": 1.0}},
        )
        painter.end()
        lit_pixel = image.pixelColor(21, 34)
        assert lit_pixel.red() > lit_pixel.green()
    finally:
        load_catalog.cache_clear()


def test_external_state_svg_peripheral_changes_resource_from_signal_only(tmp_path):
    source = Path(__file__).parents[1] / "examples" / "peripherals" / "simple_relay"
    external_root = tmp_path / "peripherals"
    installed = external_root / "simple_relay"
    installed.mkdir(parents=True)
    for name in ("manifest.json", "icon.svg", "off.svg", "on.svg"):
        (installed / name).write_bytes((source / name).read_bytes())

    spec = discover_catalog((external_root,))["simple_relay"]
    renderer = renderer_for(spec.visual["renderer"], spec.visual, spec.resource_root)
    peripheral = PeripheralInstance("relay_1", "simple_relay", {"signal": "D0"}, {})

    assert spec.simulation_class == "gpio_sampled"
    assert renderer.size(peripheral) == (132, 100)
    assert renderer.selected_state({"active": {"signal": False}}) == "off"
    assert renderer.selected_state({"active": {"signal": True}}) == "on"
    image = QImage(132, 100, QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    renderer.paint(painter, None, peripheral, {"active": {"signal": True}})
    painter.end()
    assert image.pixelColor(8, 8).green() > image.pixelColor(8, 8).red()


def test_external_state_svg_switch_toggles_and_resynchronizes_input(tmp_path):
    source = Path(__file__).parents[1] / "examples" / "peripherals" / "simple_switch"
    external_root = tmp_path / "peripherals"
    installed = external_root / "simple_switch"
    installed.mkdir(parents=True)
    for name in ("manifest.json", "icon.svg", "off.svg", "on.svg"):
        (installed / name).write_bytes((source / name).read_bytes())

    spec = discover_catalog((external_root,))["simple_switch"]
    renderer = renderer_for(spec.visual["renderer"], spec.visual, spec.resource_root)
    peripheral = PeripheralInstance("switch_1", "simple_switch", {"signal": "D0"}, {})
    changes: list[tuple[str, str, int]] = []
    changed = lambda identifier, terminal, value: changes.append((identifier, terminal, value))

    renderer.mouse_press(peripheral, QPointF(4, 4), changed)
    assert changes == []
    assert renderer.selected_state({}) == "off"
    renderer.mouse_press(peripheral, QPointF(50, 25), changed)
    assert renderer.selected_state({}) == "on"
    renderer.sync_inputs(peripheral, changed)
    renderer.mouse_press(peripheral, QPointF(50, 25), changed)

    assert spec.simulation_class == "gpio_driven"
    assert changes == [
        ("switch_1", "signal", 1),
        ("switch_1", "signal", 1),
        ("switch_1", "signal", 0),
    ]
    assert renderer.selected_state({}) == "off"


def test_external_state_svg_button_stays_active_until_release_and_cancels_safely(tmp_path):
    source = Path(__file__).parents[1] / "examples" / "peripherals" / "simple_button"
    external_root = tmp_path / "peripherals"
    installed = external_root / "simple_button"
    installed.mkdir(parents=True)
    for name in ("manifest.json", "icon.svg", "released.svg", "pressed.svg"):
        (installed / name).write_bytes((source / name).read_bytes())

    spec = discover_catalog((external_root,))["simple_button"]
    renderer = renderer_for(spec.visual["renderer"], spec.visual, spec.resource_root)
    peripheral = PeripheralInstance("button_1", "simple_button", {"signal": "D0"}, {})
    changes: list[tuple[str, str, int]] = []
    changed = lambda identifier, terminal, value: changes.append((identifier, terminal, value))

    renderer.mouse_press(peripheral, QPointF(44, 27), changed)
    assert renderer.selected_state({}) == "pressed"
    renderer.mouse_release(peripheral, QPointF(200, 200), changed)
    assert renderer.selected_state({}) == "released"
    renderer.mouse_press(peripheral, QPointF(44, 27), changed)
    renderer.cancel_interactions()
    assert renderer.selected_state({}) == "released"
    renderer.sync_inputs(peripheral, changed)

    assert changes == [
        ("button_1", "signal", 1),
        ("button_1", "signal", 0),
        ("button_1", "signal", 1),
        ("button_1", "signal", 0),
    ]
