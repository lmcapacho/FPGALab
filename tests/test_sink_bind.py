from fpga_lab.peripherals.catalog import load_catalog
from fpga_lab.profile import BoardProfile
from fpga_lab.sink_bind import bind_terminal, bits_per_channel
from fpga_lab.wiring import ResolvedWire


def test_pcf_bit_select_maps_to_port_index():
    profile = BoardProfile("x", {"clk": 1}, {"foo": 8, "bar": 1}, {"foo": 8}, "clk")
    wire = ResolvedWire("vga_1", "r0", "D2", "foo[3]")
    result = bind_terminal(wire, profile)
    assert result.error is None
    assert result.bound.port_index == tuple(profile.outputs).index("foo")
    assert result.bound.bit == 3


def test_inout_net_is_distinct_error():
    profile = BoardProfile("x", {"clk": 1, "gpio": 8}, {"led": 1}, {"led": 1}, "clk")
    wire = ResolvedWire("vga_1", "hsync", "D0", "gpio[0]")
    result = bind_terminal(wire, profile)
    assert result.bound.port_index == -1
    assert result.error and "inputs" in result.error


def test_six_bit_component_uses_two_bits_per_channel():
    catalog = load_catalog()
    assert bits_per_channel(catalog["vga_monitor"], {}) == 1
    assert bits_per_channel(catalog["vga_6bit"], {}) == 2
    assert bits_per_channel(catalog["vga_12bit"], {}) == 4
