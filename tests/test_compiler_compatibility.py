from pathlib import Path

from fpga_lab.compiler import (
    BuildRequest, VerilatorCompiler, verilator_compatibility_flags, verilator_optimization_flags,
)
from fpga_lab.profile import BoardProfile


def _write(tmp_path: Path, source: str) -> Path:
    path = tmp_path / "main.v"
    path.write_text(source, encoding="utf-8")
    return path


def test_repeated_continuous_assignment_enables_dfg_workaround(tmp_path):
    verilog = _write(tmp_path, "assign label_out = a;\nassign label_out = b;\n")

    assert verilator_compatibility_flags(verilog) == ("-fno-dfg",)


def test_normal_fanout_keeps_standard_optimization(tmp_path):
    verilog = _write(tmp_path, "assign first = source;\nassign second = source;\n")

    assert verilator_compatibility_flags(verilog) == ()


def test_manual_modes_override_automatic_detection(tmp_path):
    verilog = _write(tmp_path, "assign repeated = a;\nassign repeated = b;\n")

    assert verilator_optimization_flags(verilog, "standard") == ()
    assert verilator_optimization_flags(verilog, "compatibility") == ("-fno-dfg",)


def test_compatibility_flags_are_passed_to_verilator(tmp_path, monkeypatch):
    verilog = _write(tmp_path, "module main; endmodule\n")
    executable = tmp_path / "verilator"
    executable.touch()
    profile = BoardProfile("Test", {}, {}, {}, None)
    request = BuildRequest(
        verilog=verilog,
        profile=profile,
        top_module="main",
        build_dir=tmp_path / "build",
        verilator=str(executable),
        verilator_flags=("-fno-dfg",),
    )

    _, arguments = VerilatorCompiler().prepare(request)

    assert "-fno-dfg" in arguments
