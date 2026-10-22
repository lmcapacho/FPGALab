"""Locations and compatibility checks for versioned, private build SDKs."""

from __future__ import annotations

import json
import os
import platform
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from .i18n import t


class SDKValidationError(ValueError):
    pass


def user_toolchains_root() -> Path:
    """Return persistent application data, never the managed compilation cache."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
        return base / "FPGALab/toolchains"
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/FPGALab/toolchains"
    configured = os.environ.get("XDG_DATA_HOME", "")
    base = Path(configured) if configured and Path(configured).is_absolute() else Path.home() / ".local/share"
    return base / "FPGALab/toolchains"


def bundled_toolchains_root() -> Path | None:
    """Locate portable SDKs beside the frozen executable, not cwd or _MEIPASS."""
    if not getattr(sys, "frozen", False):
        return None
    return Path(sys.executable).resolve().parent / "toolchains"


def sdk_candidates(directory: Path | None) -> tuple[Path, ...]:
    if directory is None or not directory.is_dir():
        return ()
    # Stable natural ordering within each location; never depend on mtime.
    def key(path):
        return tuple((1, int(part)) if part.isdigit() else (0, part)
                     for part in re.split(r"(\d+)", path.name))
    return tuple(sorted((path for path in directory.iterdir() if path.is_dir()), key=key, reverse=True))


def host_glibc() -> tuple[int, int] | None:
    try:
        value = os.confstr("CS_GNU_LIBC_VERSION") or ""
    except (AttributeError, OSError, ValueError):
        return None
    match = re.fullmatch(r"glibc (\d+)\.(\d+)", value)
    return tuple(map(int, match.groups())) if match else None


@dataclass(frozen=True)
class PrivateSDK:
    root: Path
    sdk_id: str

    @classmethod
    def load(cls, directory: Path, *, expected_id: str | None = None) -> PrivateSDK:
        try:
            metadata = directory / "toolchain.json"
            if metadata.stat().st_size > 1024 * 1024:
                raise ValueError("oversized metadata")
            data = json.loads(metadata.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError) as error:
            raise SDKValidationError(t("SDK metadata is missing or invalid.")) from error
        if not isinstance(data, dict) or type(data.get("format")) is not int or data["format"] != 1:
            raise SDKValidationError(t("Unsupported SDK format."))
        if (sys.platform != "linux" or platform.machine().lower() not in ("x86_64", "amd64") or
                data.get("platform") != "linux-x86_64"):
            raise SDKValidationError(t("SDK platform is not compatible with this computer."))
        recipe = data.get("recipe")
        sdk_id = recipe.get("id") if isinstance(recipe, dict) else None
        if (data.get("status") != "experimental-controlled-build" or not isinstance(sdk_id, str) or
                not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,127}", sdk_id) or
                (expected_id is not None and expected_id != sdk_id)):
            raise SDKValidationError(t("SDK identity or build type is not supported."))
        packages = data.get("packages")
        if (not isinstance(packages, dict) or not all(isinstance(packages.get(name), str) and packages[name]
                for name in ("verilator", "make", "g++", "python3", "perl")) or
                not re.match(r"^(?:\d+:)?(?:[5-9]|[1-9]\d+)\.", packages["verilator"])):
            raise SDKValidationError(t("SDK tool versions are missing or unsupported."))
        required = re.fullmatch(r"glibc (\d+)\.(\d+)", str(data.get("glibc", "")))
        actual = host_glibc()
        if required is None or actual is None or actual < tuple(map(int, required.groups())):
            raise SDKValidationError(t("SDK requires a compatible host glibc: {version}.", version=data.get("glibc", "?")))
        root = directory.resolve()
        # The initial Make/wrapper layout is not qualified for whitespace paths.
        if any(character.isspace() for character in str(root)):
            raise SDKValidationError(t("This SDK does not support paths containing whitespace."))
        required_paths = [*(f"bin/{name}" for name in ("verilator", "make", "g++", "python3", "perl", "sh")),
                          "rootfs/lib64/ld-linux-x86-64.so.2", "rootfs/usr/share/verilator/include/verilated.h"]
        for relative in required_paths:
            path = root / relative
            if (not path.is_file() or not path.resolve().is_relative_to(root) or
                    (relative.startswith("bin/") and not os.access(path, os.X_OK))):
                raise SDKValidationError(t("SDK is incomplete or has an invalid resource: {path}.", path=relative))
        return cls(root, sdk_id)

    def environment(self) -> dict[str, str]:
        environment = os.environ.copy()
        for key in ("LD_LIBRARY_PATH", "LD_PRELOAD", "CC", "CXX", "MAKEFLAGS", "MFLAGS",
                    "GCC_EXEC_PREFIX", "COMPILER_PATH", "LIBRARY_PATH", "CPATH",
                    "CPLUS_INCLUDE_PATH", "C_INCLUDE_PATH", "VERILATOR_ROOT", "YOSYSHQ_ROOT"):
            environment.pop(key, None)
        environment["PATH"] = str(self.root / "bin")
        environment["VERILATOR_ROOT"] = str(self.root / "rootfs/usr/share/verilator")
        return environment
