from fpga_lab.simulation_worker import SimulationFrame, VgaSnapshot


def test_blank_vs_keep_pixels():
    keep = VgaSnapshot(seq=0, pixels=None)
    blank = VgaSnapshot(seq=0, pixels=b"")
    assert keep.pixels is None
    assert blank.pixels == b""
    frame = SimulationFrame(led_brightness=(0.0,) * 8, outputs={}, sinks={"vga_1": keep})
    assert frame.sinks["vga_1"].pixels is None
