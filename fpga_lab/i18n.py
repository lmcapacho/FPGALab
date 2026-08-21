"""Small runtime translation layer for the FPGALab interface."""

from __future__ import annotations

from PyQt6.QtCore import QObject, QSettings, pyqtSignal


class LanguageManager(QObject):
    """Persist and publish the interface language without external translation files."""

    language_changed = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        stored = QSettings("FPGALab", "FPGALab").value("ui/language", "en")
        self._language = stored if stored in {"en", "es"} else "en"

    @property
    def language(self) -> str:
        return self._language

    def set_language(self, language: str) -> None:
        if language not in {"en", "es"} or language == self._language:
            return
        self._language = language
        QSettings("FPGALab", "FPGALab").setValue("ui/language", language)
        self.language_changed.emit(language)


language_manager = LanguageManager()


def t(english: str, spanish: str | None = None, /, **values: object) -> str:
    """Return the active translation, formatting named placeholders when present."""
    text = spanish if language_manager.language == "es" and spanish is not None else english
    return text.format(**values)
