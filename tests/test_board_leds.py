"""Integrated LED frames follow the active board, regardless of LED count or names."""

import os
from dataclasses import replace
from time import perf_counter
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from fpga_lab.board_layout import BoardLayout, bundled_layout
from fpga_lab.board_view import BoardView
from fpga_lab.simulation import VerilatorSimulation
from fpga_lab.simulation_worker import SimulationFrame, SimulationWorker
from fpga_lab.temporal import SignalWindow
from fpga_lab.virtual_lab import FPGAVirtualLab


_APPLICATION = QApplication.instance() or QApplication([])


class FakeSimulation:
    profile = SimpleNamespace(outputs={"status_a": 1, "status_b": 1})

    def set_observation_divisor(self, _divisor):
        pass

    def reset(self):
        pass

    def streaming_reset(self):
        pass

    def ticks(self, _cycles):
        pass

    def observed_windows(self, cycles):
        return {
            "status_a[0]": SignalWindow(True, True, cycles, cycles, 0),
            "status_b[0]": SignalWindow(False, False, 0, cycles, 0),
        }

    def temporal_probe_window(self):
        return (), 0, (), ()

    def temporal_pulse_window(self):
        return ()

    def edge_window(self):
        return 0, (), 0

    def get_output(self, _name):
        return 0


def test_worker_uses_configured_led_count_and_sources():
    worker = SimulationWorker(
        FakeSimulation(), led_sources={1: ("status_b", 0)},
        led_endpoints=("status_a", "status_b"),
    )
    frames = []
    failures = []
    worker.state_changed.connect(frames.append)
    worker.failure.connect(failures.append)

    worker._last_frame_time = perf_counter() - 0.02
    worker._run_frame()
    assert not failures
    assert len(frames[-1].led_brightness) == 2
    assert frames[-1].led_brightness[0] > 0.0
    assert frames[-1].led_brightness[1] == 0.0

    worker.power_off()

    assert worker._led_sources == {0: ("status_a", 0), 1: ("status_b", 0)}
    assert frames[-1].led_brightness == (0.0, 0.0)


def test_worker_applies_active_low_before_led_persistence():
    worker = SimulationWorker(
        FakeSimulation(), led_endpoints=("status_a", "status_b", "unmapped"),
        led_active_low=(True, True, True),
    )
    frames = []
    worker.state_changed.connect(frames.append)
    worker._last_frame_time = perf_counter() - 0.02
    worker._run_frame()
    assert frames[-1].led_brightness == (0.0, 1.0, 0.0)
    worker.power_off()
    assert frames[-1].led_brightness == (0.0, 0.0, 0.0)


def test_virtual_board_paints_leds_in_declared_order(tmp_path):
    lab_file = tmp_path / "lab.json"
    lab_file.write_text('{"peripherals": []}', encoding="utf-8")
    lab = FPGAVirtualLab(lab_file=lab_file)
    lab._board = replace(lab._board, led_endpoints=("status_a", "status_b"))
    painted = []
    lab._board_view.set_led_brightness = lambda endpoint, level: painted.append((endpoint, level))
    lab._peripherals.update_frame = lambda _frame: None
    lab._running = True

    lab._paint_state(SimulationFrame(led_brightness=(0.25, 0.75), outputs={}))

    assert painted == [("status_a", 0.25), ("status_b", 0.75)]
    lab.close()
    lab.deleteLater()


def test_board_led_endpoint_can_differ_from_visual_signal():
    layout = BoardLayout.load(bundled_layout())
    first = replace(layout.elements[0], id="status", signal="hdl_status")
    view = BoardView(replace(layout, elements=(first, *layout.elements[1:])), lambda *_args: None)

    view.set_led_brightness("status", 0.5)

    assert view._led_items["status"]._intensity > 0.0
    view.deleteLater()


def test_native_binding_led_helper_accepts_board_endpoints():
    model = SimpleNamespace(
        _getters={"status_a": object(), "status_b": object()},
        get_output=lambda name: int(name == "status_b"),
    )

    assert VerilatorSimulation.read_leds(model, ("status_a", "status_b")) == [False, True]
