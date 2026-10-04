"""Persistence coverage for simulation runtime settings."""

from __future__ import annotations

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication

from fpga_lab.simulation_settings import SimulationSettings, SimulationSettingsDialog


def test_simulation_settings_round_trip(tmp_path):
    store = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    expected = SimulationSettings(
        clock_hz=25_175_000, ui_refresh_hz=75, observation_hz=2_000_000,
        verilator_optimization="compatibility",
    )

    expected.save(store)

    assert SimulationSettings.load(store, default_clock_hz=25_175_000) == expected
    assert not store.contains(SimulationSettings.CLOCK_KEY)


def test_simulation_settings_use_safe_defaults_for_invalid_values(tmp_path):
    store = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    store.setValue(SimulationSettings.CLOCK_KEY, 0)
    store.setValue(SimulationSettings.UI_REFRESH_KEY, "invalid")
    store.setValue(SimulationSettings.OBSERVATION_KEY, -1)
    store.setValue(SimulationSettings.VERILATOR_OPTIMIZATION_KEY, "turbo")

    assert SimulationSettings.load(store) == SimulationSettings()


def test_command_line_overrides_do_not_replace_unspecified_values():
    stored = SimulationSettings(clock_hz=12_000_000, ui_refresh_hz=50, observation_hz=500_000)

    overridden = stored.with_overrides(clock_hz=25_000_000)

    assert overridden == SimulationSettings(clock_hz=25_000_000, ui_refresh_hz=50, observation_hz=500_000)


def test_restoring_dialog_defaults_uses_the_selected_board_clock():
    app = QApplication.instance() or QApplication([])
    dialog = SimulationSettingsDialog(
        SimulationSettings(clock_hz=25_175_000, observation_hz=20_000_000),
        board_clock_hz=16_000_000,
        clock_override_hz=25_175_000,
    )

    assert dialog.clock_override_hz() == 25_175_000
    dialog._observation_hz.setValue(30_000_000)
    assert "exceeds the virtual clock" in dialog._effective_sampling.text()
    dialog._restore_defaults()
    assert dialog.clock_override_hz() is None
    assert dialog.values().clock_hz == 16_000_000
    dialog.close()
