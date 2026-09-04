from pathlib import Path

from fpga_lab.board import BoardDefinition, bundled_board_definition
from fpga_lab.wiring import VirtualLabProject


def test_resolve_led_fixture():
    board = BoardDefinition.load(bundled_board_definition())
    project = VirtualLabProject.load(Path(__file__).parent / "fixtures/labs/led.lab.json")
    wires = project.resolve(board, [])
    assert wires[0].board_endpoint == "D0"
    assert wires[0].hdl_net is None


def test_resolve_vga_6bit_lab():
    board = BoardDefinition.load(bundled_board_definition())
    project = VirtualLabProject.load(Path(__file__).parents[1] / "fpga_lab/assets/labs/vga_640x480_6bit.lab.json")
    wires = project.resolve(board, [])
    assert {wire.terminal for wire in wires} == {"hsync", "vsync", "r0", "r1", "g0", "g1", "b0", "b1"}


def test_resolve_display_common_supply(tmp_path):
    path = tmp_path / "display.lab.json"
    path.write_text(
        '''{
  "peripherals": [{
    "id": "display_1",
    "type": "seven_segment",
    "connections": {"a": "D0", "common": "GND"},
    "properties": {"common": "cathode"}
  }]
}\n''',
        encoding="utf-8",
    )
    board = BoardDefinition.load(bundled_board_definition())
    wires = VirtualLabProject.load(path).resolve(board, [])
    assert [(wire.terminal, wire.board_endpoint, wire.hdl_net) for wire in wires] == [
        ("a", "D0", None),
        ("common", "GND", None),
    ]


def test_unknown_type_fails(tmp_path):
    path = tmp_path / "bad.lab.json"
    path.write_text('{"peripherals":[{"id":"x","type":"nope","connections":{}}]}\n', encoding="utf-8")
    try:
        VirtualLabProject.load(path).resolve(BoardDefinition.load(bundled_board_definition()), [])
    except ValueError as error:
        assert "Unknown peripheral type" in str(error)
    else:
        raise AssertionError("expected unknown type")
