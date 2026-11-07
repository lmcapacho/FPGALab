"""Engine lifecycle and virtual-time transport without Qt or real-time sleeps."""

from types import SimpleNamespace

import pytest

from fpga_lab.simulation import EdgeEvent
from fpga_lab.simulation_engine import SimulationEngine


class Model:
    def __init__(self, clock_name="clk"):
        self.profile = SimpleNamespace(clock_name=clock_name, outputs={"echo": 1})
        self.cycle = 0
        self.value = 0
        self.closed = 0
        self.queued = []
        self.dropped = 0
        self.fail = False
        self.copied = None
        self.stream_resets = 0

    def set_observation_divisor(self, value):
        self.divisor = value

    def ticks(self, cycles):
        if self.fail:
            raise RuntimeError("model failure")
        self.cycle += cycles

    def get_output(self, name):
        return self.value

    def set_input(self, name, value):
        self.value = value

    def observed_windows(self, cycles):
        return {}

    def temporal_probe_window(self):
        return (2,), 4, (False,), (2,)

    def temporal_pulse_window(self):
        return (2, None)

    def edge_window(self):
        return self.cycle, (EdgeEvent(self.cycle, 0, True),), self.dropped

    def configure_drive_channels(self, channels):
        self.queued.clear()

    def drive_cycle(self):
        return self.cycle

    def enqueue_drive_events(self, events):
        self.queued.append(list(events))

    def configure_vga(self, timing, channels):
        return 1

    def vga_copy_front(self, *args):
        return self.copied

    def reset(self):
        self.cycle = 0
        self.value = 0
        self.queued.clear()

    def streaming_reset(self):
        self.stream_resets += 1

    def close(self):
        self.closed += 1


def test_engine_virtual_time_fractional_cycles_pause_cap_and_failure():
    model = Model()
    engine = SimulationEngine(model, 1000, observation_hz=100)
    assert model.divisor == 10
    assert engine.advance(10) is None
    engine.play()
    assert engine.advance(0.0005).cycles == 0
    assert engine.advance(0.0005).cycles == 1
    engine.pause()
    assert engine.advance(20) is None
    assert model.cycle == 1
    engine.play()
    for _ in range(10):
        frame = engine.advance(0.2)
        assert frame.cycles == 100
    assert frame.virtual_hz == pytest.approx(500)
    assert frame.temporal.elapsed_seconds == 0.1
    assert frame.temporal.pulse_high_seconds == (0.02, None)
    assert frame.edge_stream.cycle == model.cycle
    assert frame.edge_stream.events[0].cycle == model.cycle
    for elapsed in (float("nan"), float("inf"), -1):
        with pytest.raises(ValueError):
            engine.advance(elapsed)
    model.fail = True
    with pytest.raises(RuntimeError, match="model failure"):
        engine.advance(0.001)
    assert not engine.running
    engine.close()
    engine.close()
    assert model.closed == 1
    with pytest.raises(RuntimeError, match="closed"):
        engine.play()


def test_engine_serial_queue_reset_overflow_and_vga_frame_states():
    model = Model()
    engine = SimulationEngine(model, 1_000_000)
    engine.configure_drive_channels([("rx", 0, True)])
    with pytest.raises(ValueError, match="Start"):
        engine.send_uart(0, 100_000, "A")
    engine.configure_vga_bindings([SimpleNamespace(
        peripheral_id="monitor", timing=SimpleNamespace(h_active=1, v_active=1),
        channels={}, missing_required=(), bind_errors=())])
    engine.play()
    assert engine.send_uart(0, 100_000, "A") == 1
    assert engine.send_uart(0, 100_000, "B") == 1
    assert model.queued[0][0] == (0, 1, False)
    assert model.queued[1][0][1] > model.queued[0][-1][1]
    frame = engine.advance(0.001)
    assert frame.sinks["monitor"].pixels is None
    model.copied = (b"rgb", SimpleNamespace(seq=4))
    assert engine.advance(0.001).sinks["monitor"].pixels == b"rgb"
    model.dropped = 5
    frame = engine.advance(0.001)
    assert frame.edge_stream.dropped == 5 and frame.edge_stream.events == ()
    assert engine.reset() is None and engine.running
    assert model.cycle == 0 and not model.queued
    engine.send_uart(0, 100_000, "C")
    assert model.queued[-1][0] == (0, 1, False)
    blank = engine.power_off()
    assert blank.outputs == {} and blank.sinks["monitor"].pixels == b""
    assert blank.edge_stream.events == () and not engine.running
    assert not model.queued and model.stream_resets == 2
    engine.play()
    engine.send_uart(0, 100_000, "D")
    assert model.queued[-1][0] == (0, 1, False)
    engine.close()


def test_combinational_engine_does_not_publish_after_power_off():
    model = Model(clock_name=None)
    engine = SimulationEngine(model, 1000)
    assert engine.set_input("in", 1).outputs == {"echo": 1}
    assert model.cycle == 0
    engine.play()
    assert engine.advance(0.01).outputs == {"echo": 1}
    assert engine.power_off().outputs == {}
    assert engine.set_input("in", 1) is None
    assert engine.advance(1) is None
    assert engine.reset() is None
    engine.play()
    assert engine.set_input("in", 1).outputs == {"echo": 1}
    engine.close()
