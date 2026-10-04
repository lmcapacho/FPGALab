"""Persistent user settings for the simulation engine."""

from __future__ import annotations

from dataclasses import dataclass, replace

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QSpinBox, QVBoxLayout

from .i18n import t
from .board import bundled_board_clock_hz
from .theme import Metrics, style_button


@dataclass(frozen=True)
class SimulationSettings:
    """Effective clock plus global interface, sampling, and build settings."""

    clock_hz: int = bundled_board_clock_hz()
    ui_refresh_hz: int = 60
    observation_hz: int = 1_000_000
    verilator_optimization: str = "automatic"

    CLOCK_KEY = "simulation/clock_hz"
    UI_REFRESH_KEY = "simulation/ui_refresh_hz"
    OBSERVATION_KEY = "simulation/observation_hz"
    VERILATOR_OPTIMIZATION_KEY = "simulation/verilator_optimization"
    VERILATOR_OPTIMIZATION_MODES = ("automatic", "standard", "compatibility")

    @classmethod
    def load(cls, settings: QSettings | None = None, *, default_clock_hz: int | None = None) -> "SimulationSettings":
        store = settings if settings is not None else QSettings("FPGALab", "FPGALab")
        defaults = cls()
        return cls(
            clock_hz=default_clock_hz if default_clock_hz is not None else defaults.clock_hz,
            ui_refresh_hz=_positive_setting(store, cls.UI_REFRESH_KEY, defaults.ui_refresh_hz),
            observation_hz=_positive_setting(store, cls.OBSERVATION_KEY, defaults.observation_hz),
            verilator_optimization=_choice_setting(
                store, cls.VERILATOR_OPTIMIZATION_KEY, defaults.verilator_optimization,
                cls.VERILATOR_OPTIMIZATION_MODES,
            ),
        )

    def save(self, settings: QSettings | None = None) -> None:
        store = settings if settings is not None else QSettings("FPGALab", "FPGALab")
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

    def __init__(self, values: SimulationSettings, board_clock_hz: int,
                 clock_override_hz: int | None, parent=None):
        super().__init__(parent)
        self._board_clock_hz = board_clock_hz
        self.setWindowTitle(t("Simulation settings"))
        self.setMinimumSize(540, 360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Metrics.SPACE_LG, Metrics.SPACE_LG, Metrics.SPACE_LG, Metrics.SPACE_LG)
        layout.setSpacing(Metrics.SPACE_LG)
        description = QLabel(t(
            "These values apply the next time a simulation starts. They do not require rebuilding unchanged HDL."
        ))
        description.setWordWrap(True)
        layout.addWidget(description)

        form = QFormLayout()
        form.setHorizontalSpacing(Metrics.SPACE_LG)
        form.setVerticalSpacing(Metrics.SPACE_SM)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self._custom_clock = QCheckBox(t("Use a custom clock for this Lab"))
        self._custom_clock.setChecked(clock_override_hz is not None)
        self._clock_hz = _rate_field(clock_override_hz or board_clock_hz, 1_000_000_000)
        self._clock_hz.setEnabled(clock_override_hz is not None)
        self._custom_clock.toggled.connect(self._clock_hz.setEnabled)
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
        form.addRow(t("Board clock:"), QLabel(t("{rate} Hz", rate=f"{board_clock_hz:,}")))
        form.addRow(self._custom_clock, self._clock_hz)
        form.addRow(t("Interface refresh rate:"), self._ui_refresh_hz)
        form.addRow(t("Temporal sampling rate:"), self._observation_hz)
        form.addRow(t("Verilator optimization:"), self._verilator_optimization)
        layout.addLayout(form)

        note = QLabel(t(
            "Higher clock and sampling rates increase CPU usage. Interface refresh only affects visual updates."
        ))
        note.setWordWrap(True)
        layout.addWidget(note)
        self._effective_sampling = QLabel()
        self._effective_sampling.setWordWrap(True)
        self._clock_hz.valueChanged.connect(self._refresh_sampling_note)
        self._observation_hz.valueChanged.connect(self._refresh_sampling_note)
        self._custom_clock.toggled.connect(self._refresh_sampling_note)
        self._refresh_sampling_note()
        layout.addWidget(self._effective_sampling)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.RestoreDefaults
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Save
        )
        buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).setText(t("Restore defaults"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(t("Cancel"))
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(t("Save"))
        style_button(buttons.button(QDialogButtonBox.StandardButton.Save), "primary")
        buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(self._restore_defaults)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    def values(self) -> SimulationSettings:
        return SimulationSettings(
            clock_hz=self.clock_override_hz() or self._board_clock_hz,
            ui_refresh_hz=self._ui_refresh_hz.value(),
            observation_hz=self._observation_hz.value(),
            verilator_optimization=str(self._verilator_optimization.currentData()),
        )

    def clock_override_hz(self) -> int | None:
        return self._clock_hz.value() if self._custom_clock.isChecked() else None

    def _refresh_sampling_note(self) -> None:
        clock_hz = self.clock_override_hz() or self._board_clock_hz
        requested = self._observation_hz.value()
        divisor = max(1, (clock_hz + requested - 1) // requested)
        effective = clock_hz / divisor
        message = t("Effective temporal sampling: {rate:g} Hz.", rate=effective)
        if requested > clock_hz:
            message += " " + t("Requested sampling exceeds the virtual clock.")
        self._effective_sampling.setText(message)

    def _restore_defaults(self) -> None:
        defaults = SimulationSettings()
        self._custom_clock.setChecked(False)
        self._clock_hz.setValue(self._board_clock_hz)
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
