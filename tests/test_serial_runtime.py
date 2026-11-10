"""Serial peripheral state contracts without a QApplication or renderer."""

from dataclasses import FrozenInstanceError

import pytest

from fpga_lab.peripherals.serial_runtime import SpiMonitorRuntime, UartTerminalRuntime
from fpga_lab.serial_edges import Transition, uart_8n1_drive_events
from fpga_lab.wiring import PeripheralInstance


def uart_events(data, start=100):
    events, end = uart_8n1_drive_events(data, start, 1_000_000, 10_000)
    return tuple(Transition(*event) for event in events), end


def spi_events(value, offset=0):
    events = [(1, "sck", False), (1, "cs", True), (1, "mosi", False), (10, "cs", False)]
    for index in range(8):
        cycle = 12 + 4 * index
        events.extend(((cycle - 1, "mosi", bool(value & (1 << (7 - index)))),
                       (cycle, "sck", True), (cycle + 2, "sck", False)))
    events.append((46, "cs", True))
    return tuple((terminal, Transition(cycle + offset, level))
                 for cycle, terminal, level in sorted(events, key=lambda item: item[0]))


def test_uart_runtime_history_restart_errors_and_damaged_frame_recovery():
    runtime = UartTerminalRuntime({"channel": "received", "baud_property": "speed"})
    peripheral = PeripheralInstance("uart", "custom", {}, {"speed": 10_000})
    events, end = uart_events(b"A")
    assert runtime.feed_edges(peripheral, "other", events, end, 1_000_000, 0) == ""
    assert runtime.feed_edges(peripheral, "received", events[:3], 450, 1_000_000, 0) == ""
    assert runtime.feed_edges(peripheral, "received", events[3:], end, 1_000_000, 0) == "A"
    snapshot = runtime.state
    with pytest.raises(FrozenInstanceError):
        snapshot.text = "changed"
    # Stop retains output but discards partial decode and diagnostic state.
    runtime.suspend_stream()
    assert runtime.state.text == "A" and not runtime.state.configured
    assert runtime.feed_edges(peripheral, "received", events, end, 1_000_000, 0) == "A"
    assert snapshot.text == "A" and runtime.state.text == "AA"
    # A damaged frame must not be decoded, even if a caller supplies its prefix.
    damaged, end = uart_events(b"B", 2000)
    chunk = runtime.feed_edges(peripheral, "received", damaged, end, 1_000_000, 7)
    assert "overflow" in chunk and "B" not in chunk
    assert runtime.state.dropped == 7
    recovered, end = uart_events(b"C", 4000)
    assert runtime.feed_edges(peripheral, "received", recovered, end, 1_000_000, 0) == "C"
    runtime.clear_output()
    assert runtime.state.text == "" and runtime.state.dropped == 7
    # Cycle rollback (native Reset) preserves history and resets partial state.
    assert runtime.feed_edges(peripheral, "received", events, 1100, 1_000_000, 0) == "A"
    assert runtime.state.dropped == 0
    for baud in ("invalid", 600_000):
        peripheral.properties["speed"] = baud
        assert runtime.feed_edges(peripheral, "received", (), 1200, 1_000_000, 0) == ""
        assert runtime.state.invalid_baud
    peripheral.properties["speed"] = 10_000
    runtime.reset_stream()
    assert runtime.state.text == "" and not runtime.state.invalid_baud
    runtime.output_limit = 3
    events, end = uart_events(b"12345")
    assert runtime.feed_edges(peripheral, "received", events, end, 1_000_000, 0) == "12345"
    assert runtime.state.text == "345"


def test_spi_runtime_lifecycle_history_limits_and_independent_instances():
    visual = {"clock_channel": "sck", "select_channel": "cs", "mosi_channel": "mosi",
              "mode_property": "mode", "bit_order_property": "order", "cs_polarity_property": "polarity",
              "response_property": "response"}
    runtime, other = SpiMonitorRuntime(visual), SpiMonitorRuntime(visual)
    peripheral = PeripheralInstance("spi", "custom", {}, {"response": "A5"})
    runtime.response_enabled = True
    assert runtime.feed_edge_frame(peripheral, spi_events(0x31)[:8], 15, 1_000_000, 0) == ""
    runtime.suspend_stream()
    assert not runtime.state.configured
    chunk = runtime.feed_edge_frame(peripheral, spi_events(0x31), 46, 1_000_000, 0)
    assert chunk == "#1 MOSI 31  MISO TX A5\n"
    assert runtime.state.text == chunk and other.state.text == ""
    runtime.clear_output()
    assert runtime.state.configured and runtime.state.text == ""
    runtime.output_limit = 8
    assert "MOSI 31" in runtime.feed_edge_frame(peripheral, spi_events(0x31, 60), 106, 1_000_000, 0)
    assert len(runtime.state.text) == 8
    runtime.reset_stream()
    assert runtime.state.text == "" and not runtime.state.configured
    # Binding-controlled responder enablement is configuration, not RX state.
    assert runtime.response_enabled
    assert "#1 MOSI 31" in runtime.feed_edge_frame(peripheral, spi_events(0x31), 46, 1_000_000, 0)
