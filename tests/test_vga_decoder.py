from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "fpga_lab" / "native"
HARNESS = Path(__file__).parent / "native" / "vga_decoder_harness.cpp"


def _timing_cycle(h: int, v: int) -> tuple[int, int, int, int, int]:
    hsync = 0 if h < 96 else 1
    vsync = 0 if v < 2 else 1
    active = 144 <= h < 784 and 35 <= v < 515
    red = 0xF if active and h == 144 and v == 35 else 0
    green = 0xA if active else 0
    blue = 0x5 if active else 0
    return hsync, vsync, red, green, blue


@pytest.fixture(scope="module")
def harness(tmp_path_factory):
    if shutil.which("g++") is None:
        pytest.skip("g++ is required to compile the VGA decoder harness")
    build = tmp_path_factory.mktemp("vga")
    binary = build / "vga_decoder_harness"
    subprocess.check_call([
        "g++", "-std=c++17", f"-I{NATIVE}", str(HARNESS), str(NATIVE / "vga_decoder.cpp"),
        "-o", str(binary),
    ])
    return binary


def test_decoder_publishes_after_first_vsync_and_reports_h_total(harness, tmp_path):
    trace = tmp_path / "trace.txt"
    lines = []
    for frame in range(2):
        for v in range(525):
            for h in range(800):
                lines.append(" ".join(str(x) for x in _timing_cycle(h, v)))
    trace.write_text("\n".join(lines) + "\n", encoding="utf-8")
    output = subprocess.check_output([str(harness), str(trace)], text=True)
    publishes = []
    pixels = []
    for row in output.splitlines():
        parts = row.split()
        if len(parts) < 8:
            continue
        pixel_valid, sx, sy, publish, argb, last_h, synced, frames = parts
        if publish == "1":
            publishes.append((int(frames), int(last_h), int(synced)))
        if pixel_valid == "1":
            pixels.append((int(sx), int(sy), int(argb, 16) & 0x00FFFFFF))
    assert publishes, "expected at least one VSYNC publish after warmup"
    assert any(abs(last_h - 800) <= 2 for _frames, last_h, _synced in publishes)
    assert any(color & 0x00FFFFFF for _sx, _sy, color in pixels)
    origin = [pixel for pixel in pixels if pixel[0] == 0 and pixel[1] == 0]
    assert origin, "expected a pixel at (0,0) during active video"
