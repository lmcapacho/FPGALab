"""A second real board exercises catalog, constraints, and physical controls."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from fpga_lab.app import board_sources, project_clock_port
from fpga_lab.board_catalog import BoardCatalog
from fpga_lab.board_layout import BoardLayout
from fpga_lab.board_view import BoardView
from fpga_lab.ice_project import IcestudioProject
from fpga_lab.profile import BoardProfile
from fpga_lab.project_pins import ProjectPinMap
from fpga_lab.verilog_interface import VerilogInterface
from fpga_lab.virtual_lab import FPGAVirtualLab

_APPLICATION = QApplication.instance() or QApplication([])
BITSY = "icebreaker_bitsy_v1"


def test_bitsy_catalog_and_project_mapping_include_shared_led_pin(tmp_path):
    package = BoardCatalog().get(BITSY)
    assert BoardCatalog().resolve("iCEBreaker-bitsy1") == package
    assert package.definition.clock_hz == 12_000_000
    assert package.definition.pin("BTN").active_low
    pcf = tmp_path / "main.pcf"
    pcf.write_text("set_io student_clock 35\nset_io button 2\nset_io red 25\nset_io green 6\n", encoding="utf-8")
    mapping = ProjectPinMap.from_constraints(package.definition, pcf)
    assert mapping.net_for("LEDR") == mapping.net_for("P13") == "red"
    assert mapping.endpoint_for("red") == "P13"
    source = tmp_path / "main.v"
    source.write_text("module main(input student_clock, input button, output red, output green); endmodule", encoding="utf-8")
    project = IcestudioProject(tmp_path / "test.ice", tmp_path, source, pcf)
    profile = BoardProfile("Bitsy", {"student_clock": 1, "button": 1}, {"red": 1, "green": 1}, clock_name="student_clock")
    interface = VerilogInterface.discover(source)
    assert project_clock_port(project, interface, BITSY) == "student_clock"
    assert board_sources(project, profile, BITSY) == (
        {0: ("red", 0), 1: ("green", 0)}, {"BTN": ("button", 0)},
    )


def test_bitsy_button_idle_press_release_and_rerun(tmp_path):
    path = tmp_path / "test.lab"
    path.write_text('{"peripherals": []}', encoding="utf-8")
    lab = FPGAVirtualLab(board_id=BITSY, lab_file=path, input_sources={"BTN": ("button", 0)})
    lab._available_inputs = frozenset({"button"})
    changes = []
    lab.set_input_requested.connect(lambda name, value: changes.append((name, value)))
    try:
        lab.start_simulation()
        assert changes[-1] == ("button", 1)
        lab._bouncy_input("BTN", 1)
        QTest.qWait(50)
        assert changes[-1] == ("button", 0)
        lab._bouncy_input("BTN", 0)
        QTest.qWait(50)
        assert changes[-1] == ("button", 1)
        lab.stop_simulation()
        lab.start_simulation()
        assert changes[-1] == ("button", 1)
    finally:
        lab.close()
        lab.deleteLater()


def test_bitsy_svg_physical_units_match_layout_and_rotation():
    package = BoardCatalog().get(BITSY)
    view = BoardView(BoardLayout.load(package.layout_path), lambda *_args: None)
    try:
        artwork = next(item for item in view._board_group.childItems() if hasattr(item, "renderer"))
        assert artwork.mapRectToParent(artwork.boundingRect()).width() == 74
        assert artwork.mapRectToParent(artwork.boundingRect()).height() == 36
        assert round(view.sceneRect().width(), 6) == 36
        assert round(view.sceneRect().height(), 6) == 74
    finally:
        view.deleteLater()
