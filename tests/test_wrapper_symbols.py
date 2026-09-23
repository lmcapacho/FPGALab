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
    assert "sim_set_temporal_source" in source
    assert "sim_set_temporal_probe_word" in source
    assert "sim_temporal_probe_hits" in source
    assert "sim_temporal_probe_pulse_samples" in source
    assert "sim_temporal_probe_pulse_valid" in source
    assert '#include "temporal_pulse.h"' in source
    assert "sample_temporal();" in source
    assert "sim_streaming_on_posedge();" in source
    assert "sim_streaming_reset();" in source
    assert "g_top->LED0" in source
    assert "g_top->gpio_out" in source
