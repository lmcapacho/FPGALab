"""Cross-frame high-pulse measurement and virtual-time conversion."""

from pathlib import Path
import shutil
import subprocess

import pytest

from fpga_lab.peripherals.renderers.pulse_servo import pulse_to_angle
from fpga_lab.simulation_worker import pulse_samples_to_seconds


def test_pulse_samples_map_to_virtual_milliseconds_and_servo_angles():
    assert pulse_samples_to_seconds(None, 12, 12_000_000) is None
    for samples, angle in ((1000, -90), (1500, 0), (2000, 90)):
        seconds = pulse_samples_to_seconds(samples, 12, 12_000_000)
        assert seconds is not None
        assert pulse_to_angle(seconds, 1000, 2000, -90, 90) == angle
    assert pulse_to_angle(0.0005, 1000, 2000, -90, 90) == -90
    assert pulse_to_angle(0.0025, 1000, 2000, -90, 90) == 90


def test_native_probe_keeps_only_completed_pulses_across_frames(tmp_path):
    if shutil.which("g++") is None:
        pytest.skip("g++ is required to test native pulse tracking")
    root = Path(__file__).parents[1]
    binary = tmp_path / "temporal_pulse_harness"
    subprocess.run([
        "g++", "-std=c++17", f"-I{root / 'fpga_lab' / 'native'}",
        str(root / "tests" / "native" / "temporal_pulse_harness.cpp"), "-o", str(binary),
    ], check=True)
    subprocess.run([str(binary)], check=True)
