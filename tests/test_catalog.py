from fpga_lab.peripherals.catalog import load_catalog
from fpga_lab.peripherals.manifest import RESERVED_PROPERTIES
from fpga_lab.wiring import PERIPHERAL_LABELS, PERIPHERAL_TERMINALS


def test_catalog_contains_original_five_and_vga():
    catalog = load_catalog()
    assert set(catalog) >= {
        "led", "traffic_light", "seven_segment", "button", "sensor",
        "vga_monitor", "vga_6bit", "vga_12bit",
    }


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
    assert "position" not in catalog["led"].properties
    assert "position" in RESERVED_PROPERTIES


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
