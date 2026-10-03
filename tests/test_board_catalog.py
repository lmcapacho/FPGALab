"""Board package discovery must not depend on the active GUI or toolchain."""

import json

from fpga_lab.board import DEFAULT_BOARD_ID
from fpga_lab.board_catalog import BoardCatalog


def test_bundled_alhambra_ii_package_is_available():
    catalog = BoardCatalog()
    package = catalog.get(DEFAULT_BOARD_ID)

    assert catalog.resolve("alhambra-ii") == package
    assert catalog.resolve(DEFAULT_BOARD_ID) == package

    assert package.definition.board_id == "alhambra-ii"
    assert package.definition.label == "Alhambra II"
    assert package.definition.clock_hz == 12_000_000
    assert package.layout_path.is_file()
    assert package.profile_path.is_file()
    assert package.pinout_path.is_file()
    assert not catalog.diagnostics


def test_catalog_skips_invalid_package_and_keeps_valid_board(tmp_path):
    valid = tmp_path / "sample_board"
    valid.mkdir()
    (valid / "board.json").write_text(json.dumps({
        "id": "sample-board", "label": "Sample Board", "clock_hz": 1_000_000,
        "pins": [{"id": "CLK", "fpga_pin": "1", "direction": "input"}],
        "controls": {"clock": "CLK"},
    }), encoding="utf-8")
    (valid / "layout.json").write_text(json.dumps({
        "board_id": "sample_board", "svg": "board.svg",
        "viewBox": [0, 0, 100, 50], "components": [],
    }), encoding="utf-8")
    (valid / "profile.json").write_text(json.dumps({
        "board_name": "Sample Board", "inputs": {"clk": 1}, "outputs": {},
    }), encoding="utf-8")
    (valid / "board.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"/>', encoding="utf-8")
    (valid / "pinout.pcf").write_text("set_io clk 1\n", encoding="utf-8")
    invalid = tmp_path / "unfinished_board"
    invalid.mkdir()
    (invalid / "board.json").write_text("{}", encoding="utf-8")

    catalog = BoardCatalog(tmp_path)

    assert [package.board_id for package in catalog.packages] == ["sample_board"]
    assert catalog.get("sample_board").definition.clock_hz == 1_000_000
    assert len(catalog.diagnostics) == 1
    assert catalog.diagnostics[0].board_id == "unfinished_board"
    assert "layout.json" in catalog.diagnostics[0].reason
