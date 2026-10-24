"""Community locale data, fallback and selector contracts."""

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtWidgets import QApplication, QMessageBox

from fpga_lab.i18n import LanguageManager, QtDialogTranslations
from fpga_lab.locale_catalog import LocaleCatalog, valid_translation
from fpga_lab.locale_tools import source_messages, validate, write_catalog
from fpga_lab.main_window import LanguageSelector

_APPLICATION = QApplication.instance() or QApplication([])


def test_partial_catalog_template_discovery_and_persistence(tmp_path):
    source = "Open {path}"
    write_catalog(tmp_path / "en.json", "en", "English", {source: source, "Other": "Other"})
    write_catalog(tmp_path / "pt_BR.json", "pt_BR", "Português (Brasil)",
                  {source: "Abrir {path}", "Other": ""})
    (tmp_path / "broken.json").write_text("not JSON")
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    manager = LanguageManager(directory=tmp_path, settings=settings)
    assert manager.languages == ("en", "pt_BR")
    changes = []
    manager.language_changed.connect(changes.append)
    manager.set_language("pt_BR")
    assert manager.translate(source).format(path="test") == "Abrir test"
    assert manager.translate("Other") == "Other"
    assert manager.translate("Unknown") == "Unknown"
    assert manager.language_name("pt_BR") == "Português (Brasil)"
    assert changes == ["pt_BR"]
    assert LanguageManager(directory=tmp_path, settings=settings).language == "pt_BR"
    manager.set_language("unavailable")
    assert manager.language == "pt_BR"
    selector = LanguageSelector(manager)
    assert selector.currentData() == "pt_BR" and "Português" in selector.currentText()
    assert selector.view().minimumWidth() > selector.width()
    selector.show()
    _APPLICATION.processEvents()
    assert not selector.grab().isNull()  # Exercise compact closed-label painting.
    selector.close()
    with pytest.raises(FileExistsError):
        write_catalog(tmp_path / "pt_BR.json", "pt_BR", "Português", {})
    (tmp_path / "pt_BR.json").unlink()
    assert LanguageManager(directory=tmp_path, settings=settings).language == "en"


def test_catalog_validator_checks_keys_placeholders_types_and_duplicates(tmp_path):
    keys = {"Open {path}": "Open {path}", "Value {value:.1f}": "Value {value:.1f}"}
    write_catalog(tmp_path / "en.json", "en", "English", keys)
    write_catalog(tmp_path / "fr.json", "fr", "Français", {"Open {path}": ""})
    errors, reports = validate(tmp_path, check_source=False)
    assert not errors and "0/2 translated" in reports[-1]
    data = json.loads((tmp_path / "fr.json").read_text())
    data.update({"Open {path}": "Ouvrir {wrong}", "Unknown": "Unknown"})
    (tmp_path / "fr.json").write_text(json.dumps(data))
    errors, _ = validate(tmp_path, check_source=False)
    assert any("placeholders" in error for error in errors)
    assert any("unknown source" in error for error in errors)
    manager = LanguageManager(directory=tmp_path, settings=QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    manager.set_language("fr")
    assert manager.translate("Open {path}") == "Open {path}"
    assert valid_translation("{path} {value:.1f}", "{value:.1f}: {path}")
    assert not valid_translation("{path}", "{path.__class__}")
    assert not valid_translation("{value:.1f}", "{value:d}")
    assert not valid_translation("{path}", "unclosed {")
    (tmp_path / "fr.json").write_text('{"_meta":{},"x":"a","x":"b"}')
    with pytest.raises(ValueError, match="Duplicate"):
        LocaleCatalog.load(tmp_path / "fr.json")


def test_source_extractor_collects_literals_and_manifest_labels(tmp_path):
    (tmp_path / "example.py").write_text('t("Text {path}")\nt(variable)\n')
    manifest = tmp_path / "peripherals/example/manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"label": "Example", "description": "Description",
                                    "properties": {"color": {"label": "Color"}}}))
    assert source_messages(tmp_path) == {"Text {path}", "Example", "Description", "Color"}


def test_qt_regional_language_falls_back_and_text_direction_changes():
    initial_direction = _APPLICATION.layoutDirection()
    translations = QtDialogTranslations(_APPLICATION)
    try:
        translations.set_language("es_MX")
        dialog = QMessageBox()
        dialog.setStandardButtons(QMessageBox.StandardButton.Yes)
        assert dialog.button(QMessageBox.StandardButton.Yes).text().replace("&", "") == "Sí"
        translations.set_language("ar")
        assert _APPLICATION.layoutDirection() == Qt.LayoutDirection.RightToLeft
        translations.set_language("en")
        assert _APPLICATION.layoutDirection() == Qt.LayoutDirection.LeftToRight
    finally:
        translations.dispose()
        translations.deleteLater()
        _APPLICATION.setLayoutDirection(initial_direction)
