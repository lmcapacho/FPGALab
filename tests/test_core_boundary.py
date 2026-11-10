"""Import and message contracts for the framework-free domain/build layer."""

import subprocess
import sys
from pathlib import Path

import pytest


def test_core_imports_and_build_preparation_without_qt(tmp_path):
    script = r'''
import importlib
import importlib.abc
import sys
from pathlib import Path

class NoQt(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in ('PyQt6', 'PySide6'):
            raise AssertionError('Core tried to import Qt: ' + fullname)

sys.meta_path.insert(0, NoQt())
for name in ('board', 'board_layout', 'board_catalog', 'profile', 'constraints',
             'project_pins', 'signals', 'wiring', 'sink_bind', 'temporal',
             'compiler', 'cpp_wrapper', 'simulation', 'simulation_engine', 'session', 'ice_project', 'build_cache',
             'private_toolchain', 'toolchain', 'sdk_install', 'edge_drive',
             'serial_edges', 'spi_edges', 'peripherals.catalog', 'peripherals.validate',
             'peripherals.channel_plan', 'peripherals.serial_runtime'):
    importlib.import_module('fpga_lab.' + name)

from fpga_lab.board_catalog import BoardCatalog
from fpga_lab.compiler import BuildRequest, VerilatorCompiler
from fpga_lab.profile import BoardProfile
from fpga_lab.messages import t
from fpga_lab.spi_edges import spi_response_byte

assert BoardCatalog().get('alhambra_ii').definition.clock_hz > 0
assert t('Value {value}', value=3) == 'Value 3'
assert spi_response_byte('A5') == 165
try:
    spi_response_byte('invalid')
except ValueError as error:
    assert 'hexadecimal byte' in str(error)
else:
    raise AssertionError('Invalid SPI input accepted')
workspace = Path(sys.argv[1])
verilog = workspace / 'top.v'
verilog.write_text('module top(input clk, output led); assign led=clk; endmodule')
tool = workspace / 'verilator'
tool.write_text('synthetic path; prepare must not run a compiler')
profile = BoardProfile('headless', {'clk': 1}, {'led': 1}, {}, 'clk')
target, args = VerilatorCompiler().prepare(BuildRequest(
    verilog, profile, build_dir=workspace / 'build', verilator=str(tool)))
assert '--cc' in args and (workspace / 'build/sim_main.cpp').is_file()
from fpga_lab.session import SessionService
ice = workspace / 'probe.ice'
ice.write_text('{}')
exported = workspace / 'ice-build/probe'
exported.mkdir(parents=True)
(exported / 'main.v').write_text(verilog.read_text())
prepared = SessionService(workspace / 'cache').prepare(ice)
assert prepared.module_name == 'top' and prepared.board_id == 'alhambra_ii'
assert not (workspace / 'cache').exists()
from fpga_lab.peripherals.channel_plan import build_channel_plan
from fpga_lab.wiring import VirtualLabProject, PeripheralInstance, ResolvedWire
plan = build_channel_plan(
    VirtualLabProject((PeripheralInstance('lamp', 'led', {}, {}),)),
    (ResolvedWire('lamp', 'anode', 'pin', 'led'),), profile)
assert plan.temporal_probes == (((0, 0, True),),)
assert plan.temporal_bindings == (('lamp', 'anode'),)
from fpga_lab.peripherals.serial_runtime import UartTerminalRuntime, SpiMonitorRuntime
from fpga_lab.serial_edges import uart_8n1_drive_events, Transition
uart = UartTerminalRuntime({'channel': 'rx', 'baud_property': 'baud'})
instance = PeripheralInstance('uart', 'uart_terminal', {}, {'baud': 10000})
events, end = uart_8n1_drive_events(b'A', 100, 1000000, 10000)
assert uart.feed_edges(instance, 'rx', [Transition(*event) for event in events], end, 1000000, 0) == 'A'
uart.suspend_stream()
assert uart.state.text == 'A' and not uart.state.configured
spi = SpiMonitorRuntime({'clock_channel': 'sck', 'select_channel': 'cs',
    'mosi_channel': 'mosi', 'mode_property': 'mode', 'bit_order_property': 'order',
    'cs_polarity_property': 'polarity'})
assert spi.feed_edge_frame(PeripheralInstance('spi', 'spi_monitor', {}, {}), (), 1, 1000000, 0) == ''
assert spi.state.configured
assert 'fpga_lab.lab_workspace' not in sys.modules
assert not any(name.startswith(('PyQt6', 'PySide6')) for name in sys.modules)
assert 'fpga_lab.i18n' not in sys.modules
'''
    subprocess.run([sys.executable, "-c", script, str(tmp_path)],
                   cwd=Path(__file__).parents[1], check=True)


def test_message_adapter_preserves_formatting_and_gui_language_changes(tmp_path, monkeypatch):
    from fpga_lab import messages
    from fpga_lab import i18n
    from PyQt6.QtCore import QSettings

    settings = QSettings(str(tmp_path / "language.ini"), QSettings.Format.IniFormat)
    language_manager = i18n.LanguageManager(settings=settings)
    monkeypatch.setattr(i18n, "language_manager", language_manager)
    previous = messages.set_translator(None)
    try:
        assert messages.t("Value {value:.1f}", value=2) == "Value 2.0"
        messages.set_translator(lambda source: "Valeur {missing}")
        assert messages.t("Value {value:.1f}", value=2) == "Value 2.0"
        with pytest.raises(KeyError):
            messages.t("Value {missing}")
        messages.set_translator(lambda source: language_manager.translate(source))
        language_manager.set_language("es")
        assert messages.t("clock_hz must be positive.") == "clock_hz debe ser positivo."
        assert messages.t("clock_hz must be positive.") == i18n.t("clock_hz must be positive.")
        language_manager.set_language("en")
        assert messages.t("clock_hz must be positive.") == "clock_hz must be positive."
    finally:
        messages.set_translator(previous)
