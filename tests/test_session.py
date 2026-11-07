"""Session preparation, cancellation and model ownership with synthetic inputs."""

import json
from types import SimpleNamespace

import pytest

from fpga_lab import session as module
from fpga_lab.compiler import BuildCancelled
from fpga_lab.session import SessionService


@pytest.fixture
def design(tmp_path):
    ice = tmp_path / "student.ice"
    ice.write_text("{}")
    build = tmp_path / "ice-build/student"
    build.mkdir(parents=True)
    (build / "main.v").write_text(
        "module student(input reference, input button, output red, output green); "
        "assign red=button; assign green=reference; endmodule")
    (build / "main.pcf").write_text(
        "set_io reference 35\nset_io button 2\nset_io red 25\nset_io green 6\n")
    lab = tmp_path / "shared.lab"
    lab.write_text(json.dumps({"metadata": {"board_id": "iCEBreaker-bitsy1", "virtual_clock_hz": 2_000_000},
                               "peripherals": [
                                   {"id": "lamp", "type": "led", "connections": {"anode": "P13"}},
                                   {"id": "future", "type": "future_sensor", "connections": {},
                                    "properties": {"future_setting": 5}}],
                               "annotations": [{"type": "text", "text": "Keep this"}]}))
    return ice, lab


def test_prepare_uses_lab_board_clock_and_constraints_without_rewriting(design, tmp_path):
    ice, lab = design
    original = lab.read_bytes()
    service = SessionService(tmp_path / "cache")
    prepared = service.prepare(ice, lab_file=lab)
    assert prepared.board_id == "icebreaker_bitsy_v1"
    assert prepared.clock_hz == 2_000_000
    assert prepared.profile.clock_name == "reference"
    assert prepared.led_sources == {0: ("red", 0), 1: ("green", 0)}
    assert prepared.input_sources == {"BTN": ("button", 0)}
    assert prepared.wires[0].hdl_net == "red"
    assert prepared.lab.peripherals[1].properties == {"future_setting": 5}
    assert prepared.lab_document["annotations"][0]["text"] == "Keep this"
    assert len(prepared.warnings) == 1
    assert lab.read_bytes() == original and not (tmp_path / "cache").exists()
    assert service.prepare(ice, lab_file=lab, clock_hz=3_000_000).clock_hz == 3_000_000
    assert service.prepare(ice, board_id="icebreaker_bitsy_v1").clock_hz == 12_000_000
    with pytest.raises(KeyError):
        service.prepare(ice, lab_file=lab, board_id="missing")
    lab.write_text('{"peripherals": [{"id":"bad"}]}')
    with pytest.raises(ValueError):
        service.prepare(ice, lab_file=lab)


def test_build_forwards_explicit_options_and_honors_cancellation(design, tmp_path):
    ice, lab = design
    calls = []
    cancelled = False

    class Cache:
        def build_or_reuse(self, project, profile, **kwargs):
            nonlocal cancelled
            calls.append((project, profile, kwargs))
            cancelled = True
            return SimpleNamespace(library=tmp_path / "model.so")

    service = SessionService(cache=Cache())
    prepared = service.prepare(ice, lab_file=lab)
    with pytest.raises(BuildCancelled):
        service.build(prepared, cancel_requested=lambda: True)
    assert not calls
    with pytest.raises(BuildCancelled):
        service.build(prepared, optimization_mode="compatibility", verilator="/explicit/verilator",
                      cancel_requested=lambda: cancelled)
    assert calls[0][0] == prepared.project and calls[0][1] == prepared.profile
    assert calls[0][2]["top_module"] == "student"
    assert calls[0][2]["optimization_mode"] == "compatibility"
    assert calls[0][2]["verilator"] == "/explicit/verilator"
    assert service.current is None


def test_open_replaces_old_model_before_init_and_cleans_up_failed_setup(design, tmp_path, monkeypatch):
    ice, lab = design
    service = SessionService(tmp_path / "cache")
    prepared = service.prepare(ice, lab_file=lab)
    events = []
    fail_setup = False

    class Model:
        def __init__(self, library, profile):
            self.profile = profile
            events.append("load")

        def set_observation_divisor(self, divisor):
            if fail_setup:
                raise RuntimeError("setup failed")

        def set_input(self, port, value):
            events.append((port, value))

        def close(self):
            events.append("close")

    monkeypatch.setattr(module, "VerilatorSimulation", Model)
    artifact = SimpleNamespace(library=tmp_path / "model.so")
    first = service.open(prepared, artifact)
    assert ("button", 1) in events
    with pytest.raises(ValueError):
        service.open(prepared, artifact, clock_hz=-1)
    assert service.current is first and "close" not in events
    service.open(prepared, artifact)
    assert events == ["load", ("button", 1), "close", "load", ("button", 1)]
    fail_setup = True
    with pytest.raises(RuntimeError, match="setup failed"):
        service.open(prepared, artifact)
    assert events[-3:] == ["close", "load", "close"]
    assert service.current is None
    count = events.count("close")
    service.close()
    assert events.count("close") == count
