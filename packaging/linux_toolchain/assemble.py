#!/usr/bin/env python3
"""Assemble an experimental offline Linux bundle from an app and a verified SDK."""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import tarfile
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from fpga_lab.private_toolchain import PrivateSDK


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def extract_sdk(archive, checksum, destination):
    if not re.fullmatch(r"[a-fA-F0-9]{64}", checksum) or sha256(archive) != checksum.lower():
        raise ValueError("SDK archive SHA-256 does not match the expected checksum")
    if not hasattr(tarfile, "data_filter"):
        raise RuntimeError("SDK archive extraction requires Python with tarfile.data_filter (use Python 3.12+)")
    with tarfile.open(archive, "r:gz") as source:
        members, total_size = [], 0
        for member in source:
            total_size += member.size
            if len(members) >= 200_000 or member.size < 0 or total_size > 4 * 1024**3:
                raise ValueError("SDK archive exceeds packaging limits")
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] != "toolchain":
                raise ValueError(f"Invalid SDK archive path: {member.name}")
            members.append(member)
        source.extractall(destination, members=members, filter="data")
    return destination / "toolchain"


def validate_tree(root):
    """Reject links that would break relocation or reference the build machine."""
    for path in root.rglob("*"):
        if path.is_symlink() and (os.path.isabs(os.readlink(path)) or
                                  not path.resolve().is_relative_to(root) or not path.exists()):
            raise ValueError(f"Non-portable symlink: {path}")


def assemble(app, sdk_archive, sdk_sha256, output, app_version="development", revision=""):
    if output.exists() or output.is_symlink():
        raise ValueError("Use a new output directory outside the application")
    app, sdk_archive, output = app.resolve(), sdk_archive.resolve(), output.resolve()
    if output.is_relative_to(app):
        raise ValueError("Use a new output directory outside the application")
    if any(character.isspace() for character in str(output)):
        raise ValueError("The initial Linux SDK requires output paths without whitespace")
    executable = app / "FPGALab"
    if not executable.is_file() or not os.access(executable, os.X_OK) or not (app / "_internal").is_dir():
        raise ValueError("Expected a complete executable PyInstaller onedir application")
    if (app / "toolchains").exists() or (app / "toolchains").is_symlink():
        raise ValueError("Application already contains toolchains; use a clean application build")
    validate_tree(app)
    # Validate/extract before creating final output; failed checks never overwrite a bundle.
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="fpgalab-offline-stage-", dir=output.parent) as temporary:
        stage = Path(temporary)
        sdk_root = extract_sdk(sdk_archive, sdk_sha256, stage)
        sdk = PrivateSDK.load(sdk_root)
        validate_tree(sdk_root)
        for name in ("source-packages.json", "REDISTRIBUTION.txt"):
            if not (sdk_root / name).is_file():
                raise ValueError(f"SDK redistribution inventory is missing: {name}")
        bundle = stage / "FPGALab"
        shutil.copytree(app, bundle, symlinks=True)
        target = bundle / "toolchains" / sdk.sdk_id
        target.parent.mkdir()
        sdk_root.rename(target)
        PrivateSDK.load(target, expected_id=sdk.sdk_id)
        metadata = {"format": 1, "status": "experimental-offline-bundle", "platform": "linux-x86_64",
                    "application_version": app_version, "source_revision": revision,
                    "sdk_id": sdk.sdk_id, "sdk_archive_sha256": sdk_sha256.lower()}
        (bundle / "bundle.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        (bundle / "OFFLINE-README.txt").write_text(
            "FPGALab experimental offline Linux x86-64 bundle\n\n"
            "Extract the complete folder to a path without spaces and run ./FPGALab.\n"
            "No Docker, Python, Verilator, Make or G++ installation is required.\n"
            "Open an .ice design together with its matching generated ice-build folder.\n"
            "SDK selection is automatic; explicit toolchain settings still take precedence.\n"
            "Builds are stored in the user cache, not in this package.\n"
            "Initial desktop baseline: Ubuntu 24.04 x86-64; not universal Linux support.\n"
            "This is a test artifact, not approved for public SDK redistribution.\n"
            "Retain LICENSE, NOTICE and SDK source inventory/copyright notices.\n\n"
            "Paquete experimental Linux sin conexion\n"
            "Extrae toda la carpeta en una ruta sin espacios y ejecuta ./FPGALab.\n"
            "No necesitas instalar Docker, Python, Verilator, Make ni G++.\n"
            "Abre el .ice junto a su carpeta ice-build generada correspondiente.\n"
            "El SDK se detecta automaticamente; la configuracion explicita tiene prioridad.\n"
            "Las compilaciones se guardan en la cache del usuario, no en el paquete.\n"
            "Base inicial: escritorio Ubuntu 24.04 x86-64; no cualquier Linux.\n"
            "Artefacto de prueba, no aprobado para redistribucion publica del SDK.\n",
            encoding="utf-8")
        output.mkdir()  # Refuse concurrent/existing output instead of overwriting it.
        bundle.rename(output / "FPGALab")
    archive = output / "FPGALab-linux-x86_64-offline.tar.gz"
    with tarfile.open(archive, "x:gz", compresslevel=6) as destination:
        destination.add(output / "FPGALab", arcname="FPGALab")
    with archive.with_name(archive.name + ".sha256").open("x", encoding="utf-8") as stream:
        stream.write(f"{sha256(archive)}  {archive.name}\n")
    print(f"Created experimental offline package: {archive}")
    return output / "FPGALab"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", required=True, type=Path, help="Clean PyInstaller onedir directory")
    parser.add_argument("--sdk-archive", required=True, type=Path)
    parser.add_argument("--sdk-sha256", required=True, help="Expected SDK archive digest from a trusted source")
    parser.add_argument("--output", required=True, type=Path, help="New output directory")
    parser.add_argument("--app-version", default="development")
    parser.add_argument("--revision", default="")
    args = parser.parse_args()
    assemble(args.app, args.sdk_archive, args.sdk_sha256, args.output, args.app_version, args.revision)
