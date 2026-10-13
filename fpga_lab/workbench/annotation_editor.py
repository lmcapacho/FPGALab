"""Markdown content editor; annotation geometry is edited on the canvas."""

from copy import deepcopy

from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QPlainTextEdit, QVBoxLayout

from ..i18n import t
from ..theme import style_button


class AnnotationEditor(QDialog):
    def __init__(self, annotation: dict, parent=None, *, creating=False):
        super().__init__(parent)
        self._original = deepcopy(annotation)
        self.setWindowTitle(t("Add text") if creating else t("Edit text"))
        self.resize(440, 320)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(t("Markdown text")))
        self.text_field = QPlainTextEdit(annotation.get("text", ""))
        self.text_field.setAccessibleName(t("Markdown text"))
        layout.addWidget(self.text_field)
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        layout.addWidget(self.error_label)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        for button, label, role in ((QDialogButtonBox.StandardButton.Save, "Save", "primary"),
                                    (QDialogButtonBox.StandardButton.Cancel, "Cancel", "secondary")):
            buttons.button(button).setText(t(label))
            style_button(buttons.button(button), role)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.text_field.setFocus()

    def _save(self):
        if not self.text_field.toPlainText().strip():
            self.error_label.setText(t("Enter annotation text."))
            self.error_label.show()
            self.text_field.setFocus()
            return
        self.accept()

    def value(self) -> dict:
        result = deepcopy(self._original)
        result["text"] = self.text_field.toPlainText()
        return result
