"""XDC pin assignments feed the same board mapping as PCF assignments."""

import pytest

from fpga_lab.board import BoardDefinition, bundled_board_definition
from fpga_lab.constraints import XdcParser, parse_constraints_file
from fpga_lab.ice_project import IcestudioProject
from fpga_lab.project_pins import ProjectPinMap


def test_xdc_reads_literal_and_dictionary_pins_with_bus_bits(tmp_path):
    path = tmp_path / "main.xdc"
    path.write_text(
        "set_property PACKAGE_PIN W5 [get_ports {clk}]\n"
        "set_property IOSTANDARD LVCMOS33 [get_ports {clk}]\n"
        "set_property -dict { PACKAGE_PIN U2 IOSTANDARD LVCMOS33 } [get_ports {led[0]}]\n",
        encoding="utf-8",
    )
    assert [(item.net, item.fpga_pin) for item in parse_constraints_file(path)] == [
        ("clk", "W5"), ("led[0]", "U2")
    ]


@pytest.mark.parametrize("source", [
    "set_property PACKAGE_PIN W5 [get_ports $clock]",
    "set_property PACKAGE_PIN W5 [get_ports {a b}]",
    "set_property -dict {PACKAGE_PIN W5 IOSTANDARD} [get_ports {a}]",
    "set_property PACKAGE_PIN W5 [get_ports {a}]\nset_property PACKAGE_PIN U2 [get_ports {a}]",
    "set_property PACKAGE_PIN W5 [get_ports {a}]\nset_property PACKAGE_PIN W5 [get_ports {b}]",
])
def test_xdc_rejects_unsupported_or_conflicting_pin_assignments(source):
    with pytest.raises(ValueError, match="XDC|two nets"):
        XdcParser.parse_text(source)


def test_project_discovers_main_xdc_and_tracks_it_as_source(tmp_path):
    design = tmp_path / "sample.ice"
    design.write_text("{}", encoding="utf-8")
    build = tmp_path / "ice-build" / "sample"
    build.mkdir(parents=True)
    (build / "main.v").write_text("module main; endmodule", encoding="utf-8")
    xdc = build / "main.xdc"
    xdc.write_text("set_property PACKAGE_PIN W5 [get_ports {clk}]", encoding="utf-8")
    project = IcestudioProject.discover(design)
    assert project.constraints_path == xdc
    assert xdc in project.sources


def test_xdc_uses_existing_board_endpoint_resolution(tmp_path):
    xdc = tmp_path / "main.xdc"
    xdc.write_text(
        "set_property PACKAGE_PIN 45 [get_ports {student_led}]\n", encoding="utf-8"
    )
    board = BoardDefinition.load(bundled_board_definition())
    assert ProjectPinMap.from_constraints(board, xdc).net_for("LED0") == "student_led"
