from fpga_lab.peripherals.catalog import icon_path_for, load_catalog
from fpga_lab.peripherals.manifest import RESERVED_PROPERTIES, parse_manifest
from fpga_lab.peripheral_catalog_panel import matches_catalog_spec
from fpga_lab.wiring import PERIPHERAL_LABELS, PERIPHERAL_TERMINALS


def test_catalog_contains_original_five_and_vga():
    catalog = load_catalog()
    assert set(catalog) >= {
        "led", "traffic_light", "seven_segment", "button", "sensor",
        "vga_monitor", "vga_6bit", "vga_12bit",
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
