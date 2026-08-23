"""Small, portable history of opened Icestudio designs."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QSettings


class RecentProjects:
    KEY = "projects/recent_ice_files"
    LAST_PROJECT_KEY = "projects/last_ice_file"
    LIMIT = 12

    def __init__(self, settings: QSettings | None = None):
        self._settings = settings or QSettings("FPGALab", "FPGALab")

    def paths(self) -> list[Path]:
        values = self._settings.value(self.KEY, [], type=list)
        return [Path(value) for value in values if Path(value).is_file()]

    def add(self, ice_file: str | Path) -> None:
        target = str(Path(ice_file).resolve())
        values = [target, *(str(path) for path in self.paths() if str(path.resolve()) != target)]
        self._settings.setValue(self.KEY, values[:self.LIMIT])
        self._settings.setValue(self.LAST_PROJECT_KEY, target)
        self._settings.sync()

    def last_path(self) -> Path | None:
        """Return the last valid project without attempting to build it."""
        value = self._settings.value(self.LAST_PROJECT_KEY, "", type=str)
        path = Path(value) if value else None
        return path if path is not None and path.is_file() else None

    def clear(self) -> None:
        self._settings.remove(self.KEY)
