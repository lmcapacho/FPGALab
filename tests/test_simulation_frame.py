from fpga_lab.simulation_worker import SimulationFrame, VgaSnapshot, effective_virtual_hz
from fpga_lab.main_window import _format_frequency
from fpga_lab.simulation import compile_temporal_probes


def test_blank_vs_keep_pixels():
    keep = VgaSnapshot(seq=0, pixels=None)
    blank = VgaSnapshot(seq=0, pixels=b"")
    assert keep.pixels is None
    assert blank.pixels == b""
    frame = SimulationFrame(led_brightness=(0.0,) * 8, outputs={}, sinks={"vga_1": keep})
    assert frame.sinks["vga_1"].pixels is None


def test_effective_clock_uses_uncapped_wall_time():
    assert effective_virtual_hz(1_200_000, 0.2) == 6_000_000
    assert effective_virtual_hz(0, 0.2) == 0.0


def test_clock_rate_format_keeps_useful_precision():
    assert _format_frequency(12_000_000) == "12.000 MHz"
    assert _format_frequency(999_500) == "999.500 kHz"
    assert _format_frequency(60) == "60 Hz"


def test_temporal_probe_plan_deduplicates_sources_and_compiles_masks():
    sources, probes = compile_temporal_probes([
        ((2, 0, True),),
        ((3, 1, False), (2, 0, True)),
    ])

    assert sources == ((2, 0), (3, 1))
    assert probes == (
        ((0b01,), (0b01,), True),
        ((0b11,), (0b01,), True),
    )


def test_temporal_probe_plan_preserves_impossible_predicates():
    _, probes = compile_temporal_probes([
        ((2, 0, True), (2, 0, False)),
    ])

    assert probes[0][2] is False


def test_temporal_probe_plan_scales_across_machine_words():
    conditions = tuple((index, 0, True) for index in range(65))

    sources, probes = compile_temporal_probes([conditions])

    assert len(sources) == 65
    assert probes[0][0] == ((1 << 64) - 1, 1)
    assert probes[0][1] == ((1 << 64) - 1, 1)
