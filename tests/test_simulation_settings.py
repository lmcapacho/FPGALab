"""Persistence coverage for simulation runtime settings."""

from __future__ import annotations

from PyQt6.QtCore import QSettings

from fpga_lab.simulation_settings import SimulationSettings


def test_simulation_settings_round_trip(tmp_path):
    store = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    expected = SimulationSettings(
        clock_hz=25_175_000, ui_refresh_hz=75, observation_hz=2_000_000,
        verilator_optimization="compatibility",
    )

    expected.save(store)

    assert SimulationSettings.load(store) == expected


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
