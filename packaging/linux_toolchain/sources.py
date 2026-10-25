#!/usr/bin/env python3
"""Collect exact Ubuntu sources and SDK adaptations; this is not legal approval."""

import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def fields(text):
    """Parse a single Deb822 paragraph, including a clear-signed .dsc payload."""
    if text.startswith("-----BEGIN PGP SIGNED MESSAGE-----"):
        text = text.split("\n\n", 1)[1].split("\n-----BEGIN PGP SIGNATURE-----", 1)[0]
        text = "\n".join(line[2:] if line.startswith("- ") else line for line in text.splitlines())
    result, key = {}, None
    for line in text.splitlines():
        if line.startswith((" ", "\t")) and key:
            result[key] += "\n" + line.strip()
        elif ":" in line:
            key, value = line.split(":", 1)
            if key in result:
                raise ValueError(f"Duplicate source field: {key}")
            result[key] = value.strip()
        elif line.strip():
            raise ValueError("Invalid source metadata")
    return result


def file_records(record):
    files = {}
    for line in record.get("Checksums-Sha256", "").splitlines():
        if not line.strip():
            continue
        parts = line.split()
        if (len(parts) != 3 or not re.fullmatch(r"[a-f0-9]{64}", parts[0]) or
                not parts[1].isdigit() or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.+~_-]*", parts[2]) or
                parts[2] in files):
            raise ValueError("Invalid SHA-256 source file record")
        files[parts[2]] = {"sha256": parts[0], "size": int(parts[1])}
    if not files:
        raise ValueError("Source metadata has no SHA-256 records")
    return files


def select_record(text, name, version):
    matches = []
    for paragraph in re.split(r"\n\s*\n", text.strip()):
        record = fields(paragraph)
        if record.get("Package") == name and record.get("Version") == version:
            matches.append((record, paragraph))
    if not matches:
        raise ValueError(f"Exact source unavailable in frozen APT indexes: {name}={version}")
    expected = file_records(matches[0][0])
    if any(file_records(record) != expected for record, _ in matches[1:]):
        raise ValueError(f"Conflicting source checksums: {name}={version}")
    return matches[0]


def verify_download(directory, record, name, version):
    expected = file_records(record)
    for filename, info in expected.items():
        path = directory / filename
        if (path.is_symlink() or not path.is_file() or path.stat().st_size != info["size"] or
                sha256(path) != info["sha256"]):
            raise ValueError(f"Source size/SHA-256 mismatch: {name}={version}: {filename}")
    descriptors = [filename for filename in expected if filename.endswith(".dsc")]
    if len(descriptors) != 1:
        raise ValueError("Expected exactly one authenticated .dsc file")
    descriptor = fields((directory / descriptors[0]).read_text(encoding="utf-8"))
    if descriptor.get("Source") != name or descriptor.get("Version") != version:
        raise ValueError("Source descriptor identity mismatch")
    if file_records(descriptor) != {key: value for key, value in expected.items() if key != descriptors[0]}:
        raise ValueError("Source descriptor does not cover the authenticated source files")
    actual = {path.name for path in directory.iterdir()}
    if actual != set(expected):
        raise ValueError("Unexpected files in downloaded source package")
    return expected


def source_groups(inventory):
    if not isinstance(inventory, dict) or not inventory:
        raise ValueError("Empty or invalid SDK source inventory")
    groups = {}
    for binary, item in inventory.items():
        if (not re.fullmatch(r"[a-z0-9][a-z0-9+.-]*", binary) or not isinstance(item, dict)):
            raise ValueError("Invalid binary package/source inventory")
        name, version = item.get("source"), item.get("version")
        if (not isinstance(name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9+.-]*", name) or
                not isinstance(version, str) or not re.fullmatch(r"[0-9][A-Za-z0-9.+:~-]*", version)):
            raise ValueError(f"Invalid source identity for {binary}")
        groups.setdefault((name, version), []).append(binary)
    return groups


def collect(sdk, output, repository):
    """Run only in the controlled image with signed, frozen deb-src indexes."""
    if output.exists() or output.is_symlink() or output.resolve().is_relative_to(sdk.resolve()):
        raise ValueError("Use a new source output directory outside the SDK")
    inventory_path = sdk / "source-packages.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    groups = source_groups(inventory)
    metadata = json.loads((sdk / "toolchain.json").read_text(encoding="utf-8"))
    provenance = json.loads((repository / "provenance.json").read_text(encoding="utf-8"))
    output.mkdir(parents=True)
    entries = []
    for (name, version), binaries in sorted(groups.items()):
        print(f"Collecting source {name}={version} ({len(entries) + 1}/{len(groups)})", flush=True)
        query = subprocess.run(["apt-cache", "--only-source", "showsrc", name],
                               check=True, capture_output=True, text=True)
        record, raw = select_record(query.stdout, name, version)
        expected = file_records(record)
        if shutil.disk_usage(output).free < sum(info["size"] for info in expected.values()) + 16 * 1024**2:
            raise ValueError(f"Insufficient space for source {name}={version}")
        relative = Path("packages") / name / version.replace(":", "_")
        directory = output / relative
        directory.mkdir(parents=True)
        subprocess.run(["apt-get", "source", "--download-only", "--only-source", f"{name}={version}"],
                       cwd=directory, check=True)
        downloaded = verify_download(directory, record, name, version)
        (directory / "apt-source-record.txt").write_text(raw + "\n", encoding="utf-8")
        entries.append({"source": name, "version": version, "binaries": sorted(binaries),
                        "directory": relative.as_posix(), "files": downloaded,
                        "apt_record_sha256": sha256(directory / "apt-source-record.txt")})
    shutil.copy2(inventory_path, output / "source-packages.json")
    shutil.copy2(sdk / "toolchain.json", output / "toolchain.json")
    for binary, item in inventory.items():
        notice = (sdk / item["copyright"]).resolve()
        if not notice.is_relative_to(sdk.resolve()) or not notice.is_file():
            raise ValueError(f"Missing SDK copyright: {binary}")
        destination = output / "notices" / binary / "copyright"
        destination.parent.mkdir(parents=True)
        shutil.copy2(notice, destination)
    shutil.copytree(sdk / "rootfs/usr/share/common-licenses", output / "common-licenses")
    local = output / "fpgalab"
    local.mkdir()
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    for name in ("fpga_lab", "packaging/linux_toolchain"):
        shutil.copytree(repository / name, local / name, ignore=ignore)
    for name in ("LICENSE", "NOTICE", "AUTHORS.md", "AI_USAGE.md", "pyproject.toml", "provenance.json"):
        shutil.copy2(repository / name, local / name)
    # Record every local input, not just a Git revision that may have uncommitted changes.
    for relative, checksum in provenance["files"].items():
        if sha256(local / relative) != checksum:
            raise ValueError(f"Build input changed: {relative}")
    manifest = {"format": 1, "status": "collected-not-legally-approved", "sdk_id": metadata["recipe"]["id"],
                "recipe": metadata["recipe"], "source_packages_sha256": sha256(inventory_path),
                "provenance": provenance, "sources": entries,
                "license_files": {path.name: sha256(path) for path in sorted((output / "common-licenses").iterdir())}}
    (output / "source-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (output / "README.txt").write_text(
        "Experimental FPGALab SDK source companion; NOT legal redistribution approval.\n"
        "packages/: original Ubuntu .dsc, upstream archives and Debian/Ubuntu packaging/patches.\n"
        "Files were checked against authenticated frozen APT source indexes and their .dsc.\n"
        "notices/ and common-licenses/: retained third-party copyright/license texts.\n"
        "fpgalab/: exact local build/relocation inputs, recipe, LICENSE and provenance hashes.\n"
        "From fpgalab/, run python3 packaging/linux_toolchain/container_build.py --output /tmp/new-sdk.\n"
        "Docker, network access to the frozen repository and sufficient disk space are required.\n"
        "To inspect a package, run dpkg-source -x packages/<name>/<version>/*.dsc.\n"
        "Third-party rebuilds use that package's debian/rules and Build-Depends from the .dsc,\n"
        "in an appropriate Ubuntu build environment; they are not rebuilt by the SDK assembler.\n"
        "No package source was patched or extracted during collection.\n"
        "These files do not prove bit-identical rebuilds or satisfy every licensing condition.\n"
        "Review source completeness, component-specific terms, adaptations, notices and durable\n"
        "public source access before redistribution. Student designs and Labs are not included.\n",
        encoding="utf-8")
    return manifest


def archive_sources(source, archive):
    sidecar = archive.with_name(archive.name + ".sha256")
    if archive.exists() or archive.is_symlink() or sidecar.exists() or sidecar.is_symlink():
        raise ValueError("Refusing to overwrite source archive/checksum")
    if archive.resolve().is_relative_to(source.resolve()) or not (source / "source-manifest.json").is_file():
        raise ValueError("Source archive must be outside a complete source collection")
    with tarfile.open(archive, "x:gz", compresslevel=1) as stream:
        stream.add(source, arcname="sdk-sources")
    checksum = sha256(archive)
    with sidecar.open("x", encoding="utf-8") as stream:
        stream.write(f"{checksum}  {archive.name}\n")
    return checksum


def verify_collection(sdk, source):
    """Offline gate before archiving binaries; verify coverage and all recorded content."""
    inventory = json.loads((sdk / "source-packages.json").read_text())
    groups = source_groups(inventory)
    manifest = json.loads((source / "source-manifest.json").read_text())
    metadata = json.loads((sdk / "toolchain.json").read_text())
    if (manifest.get("format") != 1 or manifest.get("status") != "collected-not-legally-approved" or
            manifest.get("recipe") != metadata["recipe"] or manifest.get("sdk_id") != metadata["recipe"]["id"] or
            manifest.get("provenance") != metadata.get("build_provenance") or
            manifest.get("source_packages_sha256") != sha256(sdk / "source-packages.json") or
            sha256(source / "source-packages.json") != sha256(sdk / "source-packages.json")):
        raise ValueError("Source collection does not match the SDK")
    seen = set()
    for entry in manifest["sources"]:
        key = (entry["source"], entry["version"])
        if key in seen or sorted(groups.get(key, [])) != entry["binaries"]:
            raise ValueError("Source coverage is incomplete or duplicated")
        seen.add(key)
        directory = (source / entry["directory"]).resolve()
        if not directory.is_relative_to(source.resolve()):
            raise ValueError("Source path escapes its collection")
        raw = directory / "apt-source-record.txt"
        if sha256(raw) != entry["apt_record_sha256"]:
            raise ValueError("Recorded APT metadata changed")
        record = fields(raw.read_text())
        if record.get("Package") != key[0] or record.get("Version") != key[1] or file_records(record) != entry["files"]:
            raise ValueError("Recorded source identity or checksums changed")
        # The retained APT record is not part of the upstream source download.
        for filename, info in entry["files"].items():
            path = directory / filename
            if path.stat().st_size != info["size"] or sha256(path) != info["sha256"]:
                raise ValueError(f"Collected source changed: {filename}")
    if seen != set(groups):
        raise ValueError("Source coverage is incomplete")
    for relative, checksum in manifest["provenance"]["files"].items():
        if sha256(source / "fpgalab" / relative) != checksum:
            raise ValueError(f"Collected adaptation changed: {relative}")
    if json.loads((source / "fpgalab/provenance.json").read_text()) != manifest["provenance"]:
        raise ValueError("Collected build provenance changed")
    licenses = {path.name: sha256(path) for path in (source / "common-licenses").iterdir()}
    if licenses != manifest["license_files"]:
        raise ValueError("Collected license texts changed")
    for binary, item in inventory.items():
        if sha256(source / "notices" / binary / "copyright") != sha256(sdk / item["copyright"]):
            raise ValueError(f"Collected copyright changed: {binary}")
    return manifest
