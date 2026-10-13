"""Annotation content and appearance editor; geometry stays on the canvas."""

from copy import deepcopy

from PyQt6.QtGui import QColor, QIcon, QPixmap
from PyQt6.QtWidgets import QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout

from ..i18n import t
from ..theme import style_button
from .annotation_style import STYLE_KEYS, annotation_color, annotation_pen


class AnnotationEditor(QDialog):
    def __init__(self, annotation: dict, parent=None, *, creating=False):
        super().__init__(parent)
        self._original = deepcopy(annotation)
        self._is_text = annotation.get("type") == "text"
        self.setWindowTitle(t("Add text") if creating else t("Edit text") if self._is_text else t("Annotation appearance"))
        self.setMinimumWidth(340)
        layout = QVBoxLayout(self)
        self.text_field = None
        if self._is_text:
            layout.addWidget(QLabel(t("Markdown text")))
            self.text_field = QPlainTextEdit(annotation.get("text", ""))
            self.text_field.setAccessibleName(t("Markdown text"))
            layout.addWidget(self.text_field)
        else:
            self._build_appearance(layout)
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        layout.addWidget(self.error_label)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        if not self._is_text:
            reset = buttons.addButton(t("Reset appearance"), QDialogButtonBox.ButtonRole.ResetRole)
            style_button(reset, "secondary")
            reset.clicked.connect(self._reset_appearance)
        for button, label, role in ((QDialogButtonBox.StandardButton.Save, "Save", "primary"),
                                    (QDialogButtonBox.StandardButton.Cancel, "Cancel", "secondary")):
            buttons.button(button).setText(t(label))
            style_button(buttons.button(button), role)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        if self.text_field is not None:
            self.resize(440, 320)
            self.text_field.setFocus()
        else:
            self.adjustSize()

    def _build_appearance(self, layout):
        form = QFormLayout()
        layout.addLayout(form)
        self._colors = {}
        for field in ("stroke_color", "fill_color"):
            value = self._original.get(field)
            self._colors[field] = value if isinstance(value, str) and QColor(value).isValid() else None
        self._color_buttons = {}
        form.addRow(t("Stroke color"), self._color_button("stroke_color", "border_strong"))
        self.stroke_width = QDoubleSpinBox()
        self.stroke_width.setRange(0.5, 8)
        self.stroke_width.setDecimals(1)
        self.stroke_width.setSingleStep(0.5)
        self.stroke_width.setValue(annotation_pen(self._original).widthF())
        form.addRow(t("Stroke width"), self.stroke_width)
        self.stroke_style = QComboBox()
        for label, value in (("Solid", "solid"), ("Dashed", "dashed"), ("Dotted", "dotted")):
            self.stroke_style.addItem(t(label), value)
        self.stroke_style.setCurrentIndex(max(0, self.stroke_style.findData(self._original.get("stroke_style", "solid"))))
        form.addRow(t("Stroke style"), self.stroke_style)
        self.fill_enabled = None
        if self._original["type"] in {"rectangle", "ellipse"}:
            self.fill_enabled = QCheckBox(t("Fill shape"))
            self.fill_enabled.setChecked(self._original.get("fill_enabled") is True)
            form.addRow(self.fill_enabled)
            fill_button = self._color_button("fill_color", "accent_surface")
            form.addRow(t("Fill color"), fill_button)
            fill_button.setEnabled(self.fill_enabled.isChecked())
            self.fill_enabled.toggled.connect(fill_button.setEnabled)

    def _color_button(self, field, fallback):
        button = QPushButton()
        style_button(button, "secondary")
        self._color_buttons[field] = (button, fallback)
        button.clicked.connect(lambda: self._choose_color(field, fallback))
        self._update_color_button(field)
        return button

    def _update_color_button(self, field):
        button, fallback = self._color_buttons[field]
        swatch = QPixmap(16, 16)
        swatch.fill(annotation_color(self._colors, field, fallback))
        button.setIcon(QIcon(swatch))
        button.setText(self._colors[field] or t("Theme color"))

    def _choose_color(self, field, fallback):
        chosen = QColorDialog.getColor(annotation_color(self._colors, field, fallback), self, t("Choose color"),
                                      QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if chosen.isValid():
            self._colors[field] = chosen.name(QColor.NameFormat.HexArgb) if chosen.alpha() < 255 else chosen.name()
            self._update_color_button(field)

    def _reset_appearance(self):
        self._colors = {field: None for field in self._colors}
        for field in self._color_buttons:
            self._update_color_button(field)
        self.stroke_width.setValue(2)
        self.stroke_style.setCurrentIndex(0)
        if self.fill_enabled is not None:
            self.fill_enabled.setChecked(False)
        self._reset_requested = True

    def _save(self):
        if self.text_field is not None and not self.text_field.toPlainText().strip():
            self.error_label.setText(t("Enter annotation text."))
            self.error_label.show()
            self.text_field.setFocus()
            return
        self.accept()

    def value(self) -> dict:
        result = deepcopy(self._original)
        if self.text_field is not None:
            result["text"] = self.text_field.toPlainText()
        else:
            if getattr(self, "_reset_requested", False):
                for field in STYLE_KEYS:
                    result.pop(field, None)
            for field, value in self._colors.items():
                if value is None:
                    result.pop(field, None)
                else:
                    result[field] = value
            for field, value, default in (("stroke_width", self.stroke_width.value(), 2),
                                           ("stroke_style", self.stroke_style.currentData(), "solid"),
                                           ("fill_enabled", self.fill_enabled.isChecked() if self.fill_enabled is not None else False, False)):
                if value != default or field in result:
                    result[field] = value
        return result
