"""Preflight checks for user-installable peripheral packages."""

import json
from pathlib import Path

from fpga_lab.peripherals.validate import validate_package, main


EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "peripherals"


def test_existing_simple_packages_validate():
    for name in ("simple_relay", "simple_switch", "simple_button", "led_bar"):
        spec, issues = validate_package(EXAMPLES / name, current_version="0.1.0rc4")
        assert spec is not None
        assert issues == []


def test_future_version_is_reported():
    spec, issues = validate_package(EXAMPLES / "pulse_servo", current_version="0.1.0rc3")
    assert spec is not None
    assert any("Requires FPGALab" in issue for issue in issues)


def test_missing_and_malformed_svg(tmp_path):
    package = tmp_path / "example"
    package.mkdir()
    source = json.loads((EXAMPLES / "simple_relay" / "manifest.json").read_text())
    source["id"] = "example"
    (package / "manifest.json").write_text(json.dumps(source))
    _, issues = validate_package(package, current_version="0.1.0rc4")
    assert any("missing state SVG" in issue for issue in issues)
    (package / "off.svg").write_text("<svg")
    (package / "on.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
    _, issues = validate_package(package, current_version="0.1.0rc4")
    assert any("Invalid SVG off.svg" in issue for issue in issues)


def test_cli_reports_failure(tmp_path, capsys):
    assert main([str(tmp_path)]) == 1
    assert "Missing manifest.json" in capsys.readouterr().out
