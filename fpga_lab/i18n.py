"""Runtime translation layer backed by contributor-editable JSON catalogs."""

from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import QCoreApplication, QLibraryInfo, QLocale, QObject, QSettings, QTranslator, pyqtSignal

from .locale_catalog import LOCALES_DIR, LocaleCatalog, valid_translation


def _available_catalogs(directory=LOCALES_DIR) -> dict[str, LocaleCatalog]:
    """Discover language files so contributors can add locales without code edits."""
    catalogs = {"en": LocaleCatalog("en", "English", (), {})}
    if directory.is_dir():
        for path in sorted(directory.glob("*.json")):
            try:
                catalog = LocaleCatalog.load(path, require_metadata=False)
            except (OSError, ValueError) as error:
                logging.getLogger(__name__).warning("Ignoring translation catalog %s: %s", path, error)
                continue
            if catalog.code != "en":
                catalogs[catalog.code] = catalog
    return catalogs


class LanguageManager(QObject):
    """Persist and publish the interface language using external catalogs."""

    language_changed = pyqtSignal(str)

    def __init__(self, *, directory=LOCALES_DIR, settings=None) -> None:
        super().__init__()
        catalogs = _available_catalogs(directory)
        self._catalogs = {code: {source: value for source, value in catalog.messages.items()
                                 if value.strip() and valid_translation(source, value)}
                          for code, catalog in catalogs.items()}
        self._names = {code: catalog.name for code, catalog in catalogs.items()}
        self._settings = settings if settings is not None else QSettings("FPGALab", "FPGALab")
        stored = self._settings.value("ui/language", "en")
        self._language = stored if isinstance(stored, str) and stored in self._catalogs else "en"

    @property
    def language(self) -> str:
        return self._language

    @property
    def languages(self) -> tuple[str, ...]:
        """Return supported language identifiers from bundled locale catalogs."""
        return tuple(self._catalogs)

    def language_name(self, code: str) -> str:
        return self._names.get(code, code)

    def set_language(self, language: str) -> None:
        if language not in self._catalogs or language == self._language:
            return
        self._language = language
        self._settings.setValue("ui/language", language)
        self.language_changed.emit(language)

    def translate(self, source: str) -> str:
        """Return the active catalog entry or the stable English source text."""
        return self._catalogs.get(self._language, {}).get(source, source)


language_manager = LanguageManager()


class QtDialogTranslations(QObject):
    """Keep Qt's built-in dialog buttons in the selected interface language."""

    def __init__(self, app: QCoreApplication) -> None:
        super().__init__(app)
        self._app = app
        self._translator: QTranslator | None = None
        language_manager.language_changed.connect(self.set_language)
        self.set_language(language_manager.language)

    def set_language(self, language: str) -> None:
        if hasattr(self._app, "setLayoutDirection"):
            self._app.setLayoutDirection(QLocale(language).textDirection())
        if self._translator is not None:
            self._app.removeTranslator(self._translator)
            self._translator.deleteLater()
            self._translator = None
        if language == "en":
            return
        translator = QTranslator(self)
        translation_dirs = (
            Path(__file__).resolve().parent / "translations",
            Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)),
        )
        for directory in translation_dirs:
            if translator.load(QLocale(language), "qtbase", "_", str(directory)):
                self._app.installTranslator(translator)
                self._translator = translator
                return
        translator.deleteLater()

    def dispose(self) -> None:
        """Disconnect and remove the translator before this manager is discarded."""
        language_manager.language_changed.disconnect(self.set_language)
        if self._translator is not None:
            self._app.removeTranslator(self._translator)
            self._translator.deleteLater()
            self._translator = None


def t(source: str, /, **values: object) -> str:
    """Translate a stable English source string and format named placeholders."""
    text = language_manager.translate(source)
    try:
        return text.format(**values)
    except (KeyError, ValueError, IndexError, AttributeError, TypeError):
        if text == source:
            raise
        return source.format(**values)
