"""Runtime translation layer backed by contributor-editable JSON catalogs."""

from __future__ import annotations

import json
from pathlib import Path

from PyQt6.QtCore import QObject, QSettings, pyqtSignal


def _load_catalog(language: str) -> dict[str, str]:
    """Load a bundled catalog; English source strings intentionally need none."""
    path = Path(__file__).parent / "locales" / f"{language}.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _available_catalogs() -> dict[str, dict[str, str]]:
    """Discover language files so contributors can add locales without code edits."""
    directory = Path(__file__).parent / "locales"
    catalogs = {"en": {}}
    if directory.is_dir():
        catalogs.update({path.stem: _load_catalog(path.stem) for path in directory.glob("*.json")})
    return catalogs


class LanguageManager(QObject):
    """Persist and publish the interface language using external catalogs."""

    language_changed = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self._catalogs = _available_catalogs()
        stored = QSettings("FPGALab", "FPGALab").value("ui/language", "en")
        self._language = stored if stored in self._catalogs else "en"

    @property
    def language(self) -> str:
        return self._language

    @property
    def languages(self) -> tuple[str, ...]:
        """Return supported language identifiers from bundled locale catalogs."""
        return tuple(self._catalogs)

    def set_language(self, language: str) -> None:
        if language not in self._catalogs or language == self._language:
            return
        self._language = language
        QSettings("FPGALab", "FPGALab").setValue("ui/language", language)
        self.language_changed.emit(language)

    def translate(self, source: str) -> str:
        """Return the active catalog entry or the stable English source text."""
        return self._catalogs.get(self._language, {}).get(source, source)


language_manager = LanguageManager()


def t(source: str, /, **values: object) -> str:
    """Translate a stable English source string and format named placeholders."""
    text = language_manager.translate(source)
    return text.format(**values)
