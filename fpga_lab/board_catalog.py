"""Discover and validate bundled board packages independently of the GUI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .board import BoardDefinition
from .board_layout import BoardLayout
from .constraints import PcfParser
from .profile import BoardProfile


@dataclass(frozen=True)
class BoardPackage:
    """A validated board directory and its user-facing metadata."""

    board_id: str
    definition: BoardDefinition
    directory: Path

    @property
    def layout_path(self) -> Path:
        return self.directory / "layout.json"

    @property
    def profile_path(self) -> Path:
        return self.directory / "profile.json"

    @property
    def pinout_path(self) -> Path:
        return self.directory / "pinout.pcf"


@dataclass(frozen=True)
class BoardDiagnostic:
    board_id: str
    reason: str


class BoardCatalog:
    """List valid board packages, retaining reasons for skipped directories."""

    def __init__(self, root: Path | None = None):
        self.root = root if root is not None else Path(__file__).parent / "assets" / "boards"
        packages: list[BoardPackage] = []
        diagnostics: list[BoardDiagnostic] = []
        if not self.root.is_dir():
            diagnostics.append(BoardDiagnostic("", f"Board directory does not exist: {self.root}"))
        else:
            for directory in sorted(path for path in self.root.iterdir() if path.is_dir()):
                try:
                    packages.append(self._load(directory))
                except (OSError, ValueError, KeyError, TypeError) as error:
                    diagnostics.append(BoardDiagnostic(directory.name, str(error)))
        self.packages = tuple(packages)
        self.diagnostics = tuple(diagnostics)

    @staticmethod
    def _load(directory: Path) -> BoardPackage:
        required = ("board.json", "layout.json", "profile.json", "board.svg", "pinout.pcf")
        missing = [name for name in required if not (directory / name).is_file()]
        if missing:
            raise ValueError(f"Missing board resources: {', '.join(missing)}")
        definition = BoardDefinition.load(directory / "board.json")
        layout = BoardLayout.load(directory / "layout.json")
        BoardProfile.load(directory / "profile.json")
        PcfParser.parse_file(directory / "pinout.pcf")
        if layout.board_id != directory.name:
            raise ValueError(f"Layout board_id {layout.board_id!r} does not match directory {directory.name!r}")
        if layout.svg.resolve() != (directory / "board.svg").resolve():
            raise ValueError("Layout must reference board.svg in its board directory")
        return BoardPackage(directory.name, definition, directory)

    def get(self, board_id: str) -> BoardPackage:
        for package in self.packages:
            if package.board_id == board_id:
                return package
        raise KeyError(f"Board {board_id!r} is not available")

    def resolve(self, identifier: str) -> BoardPackage:
        """Accept the package directory ID or its public board.json ID."""
        for package in self.packages:
            if identifier in (package.board_id, package.definition.board_id):
                return package
        raise KeyError(f"Board {identifier!r} is not available")
