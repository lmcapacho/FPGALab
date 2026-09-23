"""Catalog discovery and declarative manifest contracts."""

import json
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QPushButton

from fpga_lab.peripherals.catalog import icon_path_for, load_catalog
from fpga_lab.peripherals.manifest import RESERVED_PROPERTIES, parse_manifest
from fpga_lab.peripheral_catalog_panel import PeripheralCatalogPanel, matches_catalog_spec
from fpga_lab.wiring import PERIPHERAL_LABELS, PERIPHERAL_TERMINALS


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
    assert spec.package is None
    assert icon_path_for(spec).name == "output.svg"


def test_user_package_has_inline_uninstall_action(tmp_path, monkeypatch):
    _application = QApplication.instance() or QApplication([])
    monkeypatch.setattr("fpga_lab.peripheral_catalog_panel.user_catalog_root", lambda: tmp_path)
    (tmp_path / "simple_relay").mkdir()
    example = Path(__file__).resolve().parents[1] / "examples/peripherals/simple_relay/manifest.json"
    spec = parse_manifest(json.loads(example.read_text()))
    panel = PeripheralCatalogPanel({"simple_relay": spec, "led": load_catalog()["led"]})
    emitted = []
    panel.uninstall_requested.connect(emitted.append)
    rows = {panel._list.item(index).data(Qt.ItemDataRole.UserRole): panel._list.item(index) for index in range(panel._list.count())}
    installed_row = panel._list.itemWidget(rows["simple_relay"])
    assert installed_row is not None
    assert rows["simple_relay"].text() == ""
    assert rows["simple_relay"].icon().isNull()
    assert panel._list.itemWidget(rows["led"]) is None
    installed_row.findChild(QPushButton).click()
    assert emitted == ["simple_relay"]
    panel.close()


def test_external_examples_declare_publishable_package_metadata():
    examples = Path(__file__).parents[1] / "examples" / "peripherals"

    for manifest in sorted(examples.glob("*/manifest.json")):
        spec = parse_manifest(
            json.loads(manifest.read_text(encoding="utf-8")),
            source=str(manifest),
            resource_root=manifest.parent,
        )
        assert spec.package is not None
        assert spec.package.version
        assert spec.package.author_name
        assert spec.package.license
        assert spec.package.minimum_fpgalab


def test_signal_meter_requires_a_temporal_one_bit_output():
    root = Path(__file__).parents[1] / "examples" / "peripherals" / "pwm_meter"
    base = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    for mutation in ("terminal", "simulation", "width"):
        raw = json.loads(json.dumps(base))
        if mutation == "terminal":
            raw["visual"]["terminal"] = "missing"
        elif mutation == "simulation":
            raw["simulation"]["class"] = "gpio_sampled"
        else:
            raw["terminals"][0]["width"] = 2
        try:
            parse_manifest(raw, resource_root=root)
        except ValueError as error:
            assert "signal_meter" in str(error)
        else:
            raise AssertionError(f"Invalid signal meter {mutation} was accepted")


def test_external_servo_manifest_validates_pulse_range_and_terminal():
    root = Path(__file__).parents[1] / "examples" / "peripherals" / "pulse_servo"
    original = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    spec = parse_manifest(original, resource_root=root)
    assert spec.visual["renderer"] == "pulse_servo"
    assert spec.temporal == {"mode": "per_terminal"}
    for field, value in (("terminal", "missing"), ("pulse_min_us", 2100), ("angle_max_degrees", -100)):
        invalid = json.loads(json.dumps(original))
        invalid["visual"][field] = value
        try:
            parse_manifest(invalid, resource_root=root)
        except ValueError as error:
            assert "pulse_servo" in str(error)
        else:
            raise AssertionError(f"Invalid servo {field} was accepted")


def test_package_metadata_rejects_invalid_versions_and_urls():
    manifest = Path(__file__).parents[1] / "examples" / "peripherals" / "simple_relay" / "manifest.json"
    cases = (
        ("version", "latest", "package.version must use semantic versioning"),
        ("repository", "../repository", "package.repository must be an HTTP(S) URL"),
        ("license", "not a license", "package.license must be an SPDX-style identifier"),
    )
    for field, value, message in cases:
        raw = json.loads(manifest.read_text(encoding="utf-8"))
        raw["package"][field] = value
        try:
            parse_manifest(raw, source="simple_relay/manifest.json")
        except ValueError as error:
            assert message in str(error)
        else:
            raise AssertionError(f"Invalid package {field} was accepted")


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


def test_led_array_manifest_rejects_unknown_visual_terminals():
    raw = json.loads((Path(__file__).parents[1] / "examples" / "peripherals" / "led_bar" / "manifest.json").read_text())
    raw["visual"]["terminals"][0] = "missing"

    try:
        parse_manifest(raw, source="led_bar/manifest.json")
    except ValueError as error:
        assert "unique output terminals" in str(error)
    else:
        raise AssertionError("Invalid declarative terminal was accepted")


def test_state_svg_manifest_rejects_resources_outside_its_directory():
    raw = json.loads((Path(__file__).parents[1] / "examples" / "peripherals" / "simple_relay" / "manifest.json").read_text())
    raw["visual"]["states"]["on"] = "../on.svg"

    try:
        parse_manifest(raw, source="simple_relay/manifest.json")
    except ValueError as error:
        assert "relative SVG files" in str(error)
    else:
        raise AssertionError("Unsafe state SVG resource was accepted")


def test_state_svg_interaction_requires_an_input_terminal_and_bounded_region():
    raw = json.loads((Path(__file__).parents[1] / "examples" / "peripherals" / "simple_switch" / "manifest.json").read_text())
    raw["visual"]["interactions"][0]["region"] = [12, 8, 200, 42]

    try:
        parse_manifest(raw, source="simple_switch/manifest.json")
    except ValueError as error:
        assert "invalid state_svg interaction" in str(error)
    else:
        raise AssertionError("Out-of-bounds interaction was accepted")


def test_state_svg_rejects_mismatched_momentary_event_and_action():
    raw = json.loads((Path(__file__).parents[1] / "examples" / "peripherals" / "simple_button" / "manifest.json").read_text())
    raw["visual"]["interactions"][0]["action"] = "toggle"

    try:
        parse_manifest(raw, source="simple_button/manifest.json")
    except ValueError as error:
        assert "invalid state_svg interaction" in str(error)
    else:
        raise AssertionError("Mismatched interaction event and action were accepted")
