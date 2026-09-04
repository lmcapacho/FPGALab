from fpga_lab.cpp_wrapper import render_cpp_wrapper
from fpga_lab.profile import BoardProfile


def test_wrapper_keeps_getters_and_adds_streaming_hook():
    profile = BoardProfile(
        "Alhambra II",
        {"clk": 1, "SW1": 1},
        {"LED0": 1, "gpio_out": 8},
        {"LED0": 1},
        "clk",
    )
    source = render_cpp_wrapper(profile)
    assert "void sim_set_SW1" in source
    assert "uint64_t sim_get_LED0" in source
    assert "uint64_t sim_get_gpio_out" in source
    assert "sim_read_output" in source
    assert "sim_set_temporal_probe_count" in source
    assert "sim_set_temporal_probe_term" in source
    assert "sim_temporal_probe_hits" in source
    assert "sample_temporal();" in source
    assert "if (g_sink_enabled) sim_streaming_on_posedge();" in source
    assert "sim_streaming_reset();" in source
    assert source.index("case 0: return static_cast<uint64_t>(g_top->LED0);") < source.index(
        "case 1: return static_cast<uint64_t>(g_top->gpio_out);"
    )
    assert "case 1: return bit < 8 ? static_cast<uint8_t>((g_top->gpio_out >> bit) & 1U) : 0;" in source
