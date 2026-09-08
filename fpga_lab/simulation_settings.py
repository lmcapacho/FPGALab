"""Persistent user settings for the simulation engine."""

from __future__ import annotations

from dataclasses import dataclass, replace

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QSpinBox, QVBoxLayout

from .i18n import t


@dataclass(frozen=True)
class SimulationSettings:
    """Runtime rates shared by every Lab and Icestudio project."""

    clock_hz: int = 12_000_000
    ui_refresh_hz: int = 60
    observation_hz: int = 1_000_000
    verilator_optimization: str = "automatic"

    CLOCK_KEY = "simulation/clock_hz"
    UI_REFRESH_KEY = "simulation/ui_refresh_hz"
    OBSERVATION_KEY = "simulation/observation_hz"
    VERILATOR_OPTIMIZATION_KEY = "simulation/verilator_optimization"
    VERILATOR_OPTIMIZATION_MODES = ("automatic", "standard", "compatibility")

    @classmethod
    def load(cls, settings: QSettings | None = None) -> "SimulationSettings":
        store = settings or QSettings("FPGALab", "FPGALab")
        defaults = cls()
        return cls(
            clock_hz=_positive_setting(store, cls.CLOCK_KEY, defaults.clock_hz),
            ui_refresh_hz=_positive_setting(store, cls.UI_REFRESH_KEY, defaults.ui_refresh_hz),
            observation_hz=_positive_setting(store, cls.OBSERVATION_KEY, defaults.observation_hz),
            verilator_optimization=_choice_setting(
                store, cls.VERILATOR_OPTIMIZATION_KEY, defaults.verilator_optimization,
                cls.VERILATOR_OPTIMIZATION_MODES,
            ),
        )

    def save(self, settings: QSettings | None = None) -> None:
        store = settings or QSettings("FPGALab", "FPGALab")
        store.setValue(self.CLOCK_KEY, self.clock_hz)
        store.setValue(self.UI_REFRESH_KEY, self.ui_refresh_hz)
        store.setValue(self.OBSERVATION_KEY, self.observation_hz)
        store.setValue(self.VERILATOR_OPTIMIZATION_KEY, self.verilator_optimization)
        store.sync()

    def with_overrides(
        self,
        *,
        clock_hz: int | None = None,
        ui_refresh_hz: int | None = None,
        observation_hz: int | None = None,
    ) -> "SimulationSettings":
        """Apply command-line values without persisting them."""
        return replace(
            self,
            clock_hz=clock_hz if clock_hz is not None else self.clock_hz,
            ui_refresh_hz=ui_refresh_hz if ui_refresh_hz is not None else self.ui_refresh_hz,
            observation_hz=observation_hz if observation_hz is not None else self.observation_hz,
        )


class SimulationSettingsDialog(QDialog):
    """Compact editor for the runtime rates exposed by the command line."""

    def __init__(self, values: SimulationSettings, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("Simulation settings"))
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        description = QLabel(t(
            "These values apply the next time a simulation starts. They do not require rebuilding unchanged HDL."
        ))
        description.setWordWrap(True)
        layout.addWidget(description)

        form = QFormLayout()
        self._clock_hz = _rate_field(values.clock_hz, 1_000_000_000)
        self._ui_refresh_hz = _rate_field(values.ui_refresh_hz, 240)
        self._observation_hz = _rate_field(values.observation_hz, 1_000_000_000)
        self._verilator_optimization = QComboBox()
        for label, mode in (
            (t("Automatic (recommended)"), "automatic"),
            (t("Standard"), "standard"),
            (t("Compatibility"), "compatibility"),
        ):
            self._verilator_optimization.addItem(label, mode)
        selected_mode = self._verilator_optimization.findData(values.verilator_optimization)
        self._verilator_optimization.setCurrentIndex(max(0, selected_mode))
        self._verilator_optimization.setToolTip(t(
            "Automatic detects HDL patterns that require Verilator compatibility mode."
        ))
        form.addRow(t("Virtual FPGA clock:"), self._clock_hz)
        form.addRow(t("Interface refresh rate:"), self._ui_refresh_hz)
        form.addRow(t("Temporal sampling rate:"), self._observation_hz)
        form.addRow(t("Verilator optimization:"), self._verilator_optimization)
        layout.addLayout(form)

        note = QLabel(t(
            "Higher clock and sampling rates increase CPU usage. Interface refresh only affects visual updates."
        ))
        note.setWordWrap(True)
        layout.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.RestoreDefaults
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Save
        )
        buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).setText(t("Restore defaults"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(t("Cancel"))
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(t("Save"))
        buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(self._restore_defaults)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    def values(self) -> SimulationSettings:
        return SimulationSettings(
            clock_hz=self._clock_hz.value(),
            ui_refresh_hz=self._ui_refresh_hz.value(),
            observation_hz=self._observation_hz.value(),
            verilator_optimization=str(self._verilator_optimization.currentData()),
        )

    def _restore_defaults(self) -> None:
        defaults = SimulationSettings()
        self._clock_hz.setValue(defaults.clock_hz)
        self._ui_refresh_hz.setValue(defaults.ui_refresh_hz)
        self._observation_hz.setValue(defaults.observation_hz)
        self._verilator_optimization.setCurrentIndex(
            self._verilator_optimization.findData(defaults.verilator_optimization)
        )


def _rate_field(value: int, maximum: int) -> QSpinBox:
    field = QSpinBox()
    field.setRange(1, maximum)
    field.setValue(value)
    field.setSuffix(" Hz")
    field.setGroupSeparatorShown(True)
    return field


def _positive_setting(settings: QSettings, key: str, default: int) -> int:
    try:
        value = int(settings.value(key, default))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _choice_setting(settings: QSettings, key: str, default: str, choices: tuple[str, ...]) -> str:
    value = str(settings.value(key, default)).casefold()
    return value if value in choices else default
