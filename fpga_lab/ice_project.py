"""Descubrimiento no invasivo de artefactos generados por Icestudio."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class IcestudioProjectError(RuntimeError):
    """El diseño seleccionado no contiene artefactos ejecutables de Icestudio."""


@dataclass(frozen=True)
class IcestudioProject:
    """Un diseño ``.ice`` y su subdirectorio correspondiente de ``ice-build``."""

    ice_file: Path
    build_dir: Path
    main_v: Path
    pcf: Path | None

    @classmethod
    def discover(cls, ice_file: str | Path) -> "IcestudioProject":
        source = Path(ice_file).expanduser().resolve()
        if not source.is_file() or source.suffix.lower() != ".ice":
            raise IcestudioProjectError("Seleccione un archivo de diseño Icestudio (.ice).")

        root = source.parent / "ice-build"
        preferred = root / source.stem
        candidates = (preferred, root)
        for directory in candidates:
            main_v = directory / "main.v"
            if main_v.is_file():
                pcf = cls._pcf_in(directory)
                return cls(source, directory, main_v, pcf)

        expected = preferred / "main.v"
        raise IcestudioProjectError(
            f"No existe {expected}. Genere el Verilog desde Icestudio antes de ejecutar."
        )

    @staticmethod
    def _pcf_in(directory: Path) -> Path | None:
        main_pcf = directory / "main.pcf"
        if main_pcf.is_file():
            return main_pcf
        candidates = sorted(directory.glob("*.pcf"))
        return candidates[0] if len(candidates) == 1 else None

    @property
    def sources(self) -> tuple[Path, ...]:
        return (self.main_v,) if self.pcf is None else (self.main_v, self.pcf)
