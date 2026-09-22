import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtWidgets import QApplication

from fpga_lab.peripherals.catalog import discover_catalog, icon_path_for, load_catalog
from fpga_lab.peripherals.manifest import RESERVED_PROPERTIES, parse_manifest
from fpga_lab.peripheral_catalog_panel import matches_catalog_spec
from fpga_lab.peripherals.renderers.bcd_display import (
    active_bcd_segments,
    bcd_enable_active,
    bcd_segments,
)
from fpga_lab.peripherals.renderers.dip_switch import DipSwitchRenderer
from fpga_lab.peripherals.renderers.toggle_switch import ToggleSwitchRenderer
from fpga_lab.peripherals.renderers import renderer_for
from fpga_lab.wiring import PeripheralInstance
from PyQt6.QtCore import QPointF
from fpga_lab.wiring import PERIPHERAL_LABELS, PERIPHERAL_TERMINALS


_APPLICATION = QApplication.instance() or QApplication([])


def test_catalog_contains_original_five_and_vga():
    catalog = load_catalog()
    assert set(catalog) >= {
        "led", "traffic_light", "seven_segment", "button", "sensor",
        "bcd_display", "dip_switch", "toggle_switch", "vga_monitor", "vga_6bit", "vga_12bit",
    }


def test_catalog_metadata_supports_search_categories_and_icons():
    catalog = load_catalog()

    assert catalog["button"].category == "input"
    assert "keyboard" in catalog["button"].keywords
    assert catalog["seven_segment"].category == "display"
    assert catalog["vga_monitor"].category == "video"
    assert catalog["led"].description
    base_icons = {icon_path_for(catalog[identifier]) for identifier in (
        "button", "sensor", "led", "traffic_light", "seven_segment",
    )}
    assert len(base_icons) == 5
    assert all(path.name == "icon.svg" and path.is_file() for path in base_icons)
    assert matches_catalog_spec(catalog["button"], "keyboard")
    assert not matches_catalog_spec(catalog["button"], "keyboard", "output")
    assert matches_catalog_spec(catalog["seven_segment"], "digit", "display")


def test_catalog_metadata_remains_optional_for_third_party_manifests():
    spec = parse_manifest({
        "id": "minimal",
        "label": "Minimal",
        "simulation": {"class": "gpio_sampled"},
        "terminals": [],
        "properties": {},
        "visual": {"renderer": "lamp", "size": [10, 10]},
    })

    assert spec.category == "output"
    assert spec.description == ""
    assert spec.keywords == ()
    assert spec.icon is None
    assert icon_path_for(spec).name == "output.svg"


def test_legacy_terminal_shapes():
    assert PERIPHERAL_TERMINALS["led"] == {"anode": "output"}
    assert PERIPHERAL_TERMINALS["seven_segment"]["g"] == "output"
    assert PERIPHERAL_LABELS["button"] == "Push button"


def test_traffic_light_and_seven_segment_properties():
    catalog = load_catalog()
    colors = catalog["traffic_light"].properties["colors"]
    assert colors["type"] == "color_map"
    assert colors["default"]["red"] == "#ef4444"
    assert catalog["seven_segment"].properties["common"]["default"] == "cathode"
    display = catalog["seven_segment"]
    assert display.simulation_class == "gpio_temporal"
    assert display.temporal == {
        "mode": "display_common",
        "common_terminal": "common",
        "active_terminals": ["a", "b", "c", "d", "e", "f", "g"],
        "polarity_property": "common",
    }
    assert display.terminal_map()["common"].supplies == ("GND", "VCC")
    assert catalog["led"].simulation_class == "gpio_temporal"
    assert catalog["traffic_light"].simulation_class == "gpio_temporal"
    assert "position" not in catalog["led"].properties
    assert "position" in RESERVED_PROPERTIES


def test_button_shortcut_is_declared_by_its_manifest():
    shortcut = load_catalog()["button"].properties["shortcut"]
    assert shortcut["type"] == "key_sequence"
    assert shortcut["default"] == ""


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


def test_vga_components_have_fixed_pin_budgets():
    catalog = load_catalog()
    one = catalog["vga_monitor"]
    six = catalog["vga_6bit"]
    twelve = catalog["vga_12bit"]
    assert one.color_depth == 1
    assert six.color_depth == 2
    assert twelve.color_depth == 4
    assert one.required_terminals() == ("hsync", "vsync", "r0", "g0", "b0")
    assert six.required_terminals() == ("hsync", "vsync", "r0", "r1", "g0", "g1", "b0", "b1")
    assert "r3" in twelve.required_terminals()
    assert "r1" not in one.required_terminals()


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


def test_led_array_manifest_rejects_unknown_visual_terminals():
    raw = json.loads((Path(__file__).parents[1] / "examples" / "peripherals" / "led_bar" / "manifest.json").read_text())
    raw["visual"]["terminals"][0] = "missing"

    try:
        parse_manifest(raw, source="led_bar/manifest.json")
    except ValueError as error:
        assert "unique output terminals" in str(error)
    else:
        raise AssertionError("Invalid declarative terminal was accepted")


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


def test_state_svg_manifest_rejects_resources_outside_its_directory():
    raw = json.loads((Path(__file__).parents[1] / "examples" / "peripherals" / "simple_relay" / "manifest.json").read_text())
    raw["visual"]["states"]["on"] = "../on.svg"

    try:
        parse_manifest(raw, source="simple_relay/manifest.json")
    except ValueError as error:
        assert "relative SVG files" in str(error)
    else:
        raise AssertionError("Unsafe state SVG resource was accepted")


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


def test_state_svg_interaction_requires_an_input_terminal_and_bounded_region():
    raw = json.loads((Path(__file__).parents[1] / "examples" / "peripherals" / "simple_switch" / "manifest.json").read_text())
    raw["visual"]["interactions"][0]["region"] = [12, 8, 200, 42]

    try:
        parse_manifest(raw, source="simple_switch/manifest.json")
    except ValueError as error:
        assert "invalid state_svg interaction" in str(error)
    else:
        raise AssertionError("Out-of-bounds interaction was accepted")
