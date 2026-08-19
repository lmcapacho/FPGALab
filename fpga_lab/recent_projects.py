"""Small, portable history of opened Icestudio designs."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QSettings


class RecentProjects:
    KEY = "projects/recent_ice_files"
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

    def clear(self) -> None:
        self._settings.remove(self.KEY)
