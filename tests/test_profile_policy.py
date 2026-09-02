import pytest

from fpga_lab.profile import BoardProfile
from fpga_lab.profile_policy import ObservedProbeTooWide, apply_led_observed


def test_observed_is_full_width_of_led_ports_only():
    profile = BoardProfile(
        "Alhambra II",
        {"clk": 1},
        {"LED0": 1, "debug": 8, "hsync": 1},
        {"LED0": 1, "debug": 8, "hsync": 1},
        "clk",
    )
    narrowed = apply_led_observed(profile, {0: ("LED0", 0)})
    assert narrowed.observed == {"LED0": 1}
    assert set(narrowed.outputs) == {"LED0", "debug", "hsync"}


def test_probe_too_wide_named_error():
    outputs = {"bus0": 64, "bus1": 64}
    profile = BoardProfile("x", {"clk": 1}, outputs, outputs, "clk")
    with pytest.raises(ObservedProbeTooWide):
        apply_led_observed(profile, {0: ("bus0", 0), 1: ("bus1", 0)})
