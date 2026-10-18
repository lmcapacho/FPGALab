#!/usr/bin/env python3
"""Build an experimental relocatable SDK from installed Debian/Ubuntu packages.

This is a maintainer tool, not an installer. It never installs host packages.
Use a controlled build machine/container for a distributable release.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tarfile


ROOT_PACKAGES = ("verilator", "make", "g++", "perl", "python3", "bash", "dash", "coreutils", "findutils")


def is_executable_elf(path):
    if path.is_symlink() or not path.is_file() or re.search(r"\.so(?:\.|$)", path.name) or not os.access(path, os.X_OK):
        return False
    with path.open("rb") as stream:
        return stream.read(4) == b"\x7fELF"


def dependency_closure(records, roots):
    """Resolve installed alternatives, rejecting missing/virtual dependencies."""
    selected = set()
    providers = {}
    for name in sorted(records):
        for virtual in records[name].get("provides", ()):
            providers.setdefault(virtual, name)

    def visit(name):
        if name in selected:
            return
        if name not in records:
            raise ValueError(f"Required installed package is missing: {name}")
        selected.add(name)
        for dependency in records[name]["dependencies"].split(","):
            if not dependency.strip():
                continue
            alternatives = [re.split(r"[\s(:]", part.strip(), maxsplit=1)[0] for part in dependency.split("|")]
            chosen = next((candidate if candidate in records else providers.get(candidate)
                           for candidate in alternatives if candidate in records or candidate in providers), None)
            if chosen is None:
                raise ValueError(f"Cannot resolve dependency of {name}: {dependency}")
            visit(chosen)

    for root in roots:
        visit(root)
    return sorted(selected)


def package_records():
    output = subprocess.check_output([
        "dpkg-query", "-W", "-f=${Package}\t${Status}\t${Version}\t${Depends},${Pre-Depends}\t${Provides}\n",
    ], text=True)
    records = {}
    for line in output.splitlines():
        name, status, version, dependencies, provides = line.split("\t", 4)
        if status == "install ok installed":
            records[name] = {"version": version, "dependencies": dependencies,
                             "provides": [part.strip().split(" ")[0] for part in provides.split(",") if part.strip()]}
    return records


def write_executable(path, source):
    path.write_text(source, encoding="utf-8")
    path.chmod(0o755)


def elf_wrapper(relative_root, executable):
    """Use our loader and libraries, without leaking them into the GUI process."""
    return f'''#!/bin/sh
set -eu
sdk_root="$(CDPATH= cd -- "${{0%/*}}/{relative_root}" && pwd -P)"
unset LD_LIBRARY_PATH LD_PRELOAD
exec "$sdk_root/rootfs/lib64/ld-linux-x86-64.so.2" \\
  --library-path "$sdk_root/rootfs/usr/lib/x86_64-linux-gnu:$sdk_root/rootfs/usr/lib" \\
  "$sdk_root/{executable}" "$@"
'''


def copy_packages(destination, records, packages):
    rootfs = destination / "rootfs"
    rootfs.mkdir()
    (rootfs / "usr").mkdir()
    for alias in ("bin", "sbin", "lib", "lib64"):
        (rootfs / "usr" / alias).mkdir(exist_ok=True)
        (rootfs / alias).symlink_to(f"usr/{alias}")
    for name in packages:
        files = subprocess.check_output(["dpkg-query", "-L", name], text=True).splitlines()
        for entry in files:
            source = Path(entry)
            # Package-owned executables, headers, libraries and copyrights only;
            # never copy a user's machine configuration from /etc or /var.
            if not source.is_absolute() or source.parts[1:2] not in (("usr",), ("lib",), ("lib64",), ("bin",), ("sbin",)):
                continue
            if any(source.is_relative_to(directory) for directory in ("/usr/share/zoneinfo", "/usr/share/man", "/usr/share/info", "/usr/share/locale")):
                continue
            if source.is_relative_to("/usr/share/doc") and source.is_symlink() and not source.exists() and source.name != "copyright":
                continue
            if source.is_symlink() and source.resolve().is_relative_to("/etc"):
                continue
            target = rootfs / source.relative_to("/")
            if target.exists() or target.is_symlink():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.is_symlink():
                link = os.readlink(source)
                if link.startswith("/"):
                    if link.startswith("/etc/alternatives/"):
                        link = str(source.resolve())
                    link = os.path.relpath(rootfs / link.lstrip("/"), target.parent)
                target.symlink_to(link)
            elif source.is_dir():
                target.mkdir(exist_ok=True)
            elif source.is_file():
                shutil.copy2(source, target)
    broken_links = []
    for path in rootfs.rglob("*"):
        if path.is_symlink():
            resolved = path.resolve()
            if not resolved.is_relative_to(rootfs.resolve()) or not resolved.exists():
                broken_links.append(str(path))
    if broken_links:
        raise ValueError("SDK symlinks have no packaged target:\n" + "\n".join(broken_links))
    # GCC launches cc1plus, collect2, assembler and linker as subprocesses. Wrap
    # those as well, not only the user-facing compiler executable.
    executable_roots = [rootfs / "usr/bin", rootfs / "usr/lib/gcc", rootfs / "usr/libexec"]
    candidates = [path for directory in executable_roots if directory.exists() for path in directory.rglob("*")]
    for path in candidates:
        if not is_executable_elf(path):
            continue
        real = path.with_name(path.name + ".fpgalab-elf")
        path.rename(real)
        write_executable(path, elf_wrapper(os.path.relpath(destination, path.parent), real.relative_to(destination)))
    return rootfs


def create_launchers(destination, rootfs):
    binary_dir = destination / "bin"
    binary_dir.mkdir()
    common = '''#!/bin/sh
set -eu
sdk_root="$(CDPATH= cd -- "${0%/*}/.." && pwd -P)"
unset LD_LIBRARY_PATH LD_PRELOAD GCC_EXEC_PREFIX COMPILER_PATH LIBRARY_PATH CPATH CPLUS_INCLUDE_PATH C_INCLUDE_PATH
export LC_ALL=C
'''
    for path in sorted((rootfs / "usr/bin").iterdir()):
        if path.is_file() and not path.name.endswith(".fpgalab-elf") and os.access(path, os.X_OK):
            write_executable(binary_dir / path.name, common + f'exec "$sdk_root/rootfs/usr/bin/{path.name}" "$@"\n')
    compiler_dirs = sorted((rootfs / "usr/lib/gcc/x86_64-linux-gnu").iterdir())
    compiler = compiler_dirs[-1].relative_to(destination)
    for name in ("g++", "c++", "gcc", "cc"):
        if not (rootfs / "usr/bin" / name).exists():
            continue
        write_executable(binary_dir / name, common +
                         f'exec "$sdk_root/rootfs/usr/bin/{name}" --sysroot="$sdk_root/rootfs" '
                         f'-B"$sdk_root/{compiler}/" -B"$sdk_root/rootfs/usr/bin/" "$@"\n')
    # Debian separates the Perl launcher from its binary and fixes PYTHON3 to
    # /usr/bin/python3 in verilated.mk. Adapt those paths inside the SDK only.
    write_executable(rootfs / "usr/share/verilator/bin/verilator_bin",
                     '#!/bin/sh\nexec "${0%/*}/../../../bin/verilator_bin" "$@"\n')
    write_executable(binary_dir / "make", common +
                     'export PATH="$sdk_root/bin"\n'
                     'exec "$sdk_root/rootfs/usr/bin/make" "PYTHON3=$sdk_root/bin/python3" "PERL=$sdk_root/bin/perl" "$@"\n')
    perl_dirs = sorted({path.relative_to(destination).as_posix()
                        for pattern in ("usr/lib/*/perl-base", "usr/lib/*/perl/*", "usr/lib/*/perl5/*", "usr/share/perl/*", "usr/share/perl5")
                        for path in rootfs.glob(pattern) if path.is_dir()})
    perl_path = ":".join(f"$sdk_root/{directory}" for directory in perl_dirs)
    write_executable(binary_dir / "perl", common +
                     f'export PERL5LIB="{perl_path}"\nunset PERL5OPT PERL_LOCAL_LIB_ROOT PERL_MB_OPT PERL_MM_OPT\n'
                     'exec "$sdk_root/rootfs/usr/bin/perl" "$@"\n')
    write_executable(binary_dir / "python3", common +
                     'export PYTHONHOME="$sdk_root/rootfs/usr"\nunset PYTHONPATH\n'
                     'export PYTHONNOUSERSITE=1\nexec "$sdk_root/rootfs/usr/bin/python3" "$@"\n')
    write_executable(binary_dir / "verilator", common +
                     'export VERILATOR_ROOT="$sdk_root/rootfs/usr/share/verilator"\n'
                     'export PATH="$sdk_root/bin"\n'
                     'exec "$sdk_root/bin/perl" "$sdk_root/rootfs/usr/bin/verilator" "$@"\n')


def build(destination):
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise ValueError("This first prototype supports Debian/Ubuntu Linux x86-64 only")
    if destination.exists():
        raise ValueError(f"Refusing to overwrite an existing output: {destination}")
    if any(character.isspace() for character in str(destination)):
        raise ValueError("This initial SDK prototype requires an output path without whitespace")
    records = package_records()
    packages = dependency_closure(records, ROOT_PACKAGES)
    destination.mkdir(parents=True)
    rootfs = copy_packages(destination, records, packages)
    create_launchers(destination, rootfs)
    metadata = {
        "format": 1, "status": "experimental-local-snapshot", "platform": "linux-x86_64",
        "glibc": subprocess.check_output(["getconf", "GNU_LIBC_VERSION"], text=True).strip(),
        "build_os": platform.freedesktop_os_release(),
        "packages": {name: records[name]["version"] for name in packages},
        "redistribution": "Not release-approved: retain copyrights and audit source/license obligations before publishing",
    }
    (destination / "toolchain.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(f"Created experimental SDK: {destination} ({len(packages)} packages)")


def archive_bundle(source, archive):
    source, archive = source.resolve(), archive.resolve()
    checksum = archive.with_name(archive.name + ".sha256")
    if not (source / "toolchain.json").is_file() or archive.is_relative_to(source):
        raise ValueError("An archive must be outside a completed SDK")
    if archive.exists() or checksum.exists():
        raise ValueError("Refusing to overwrite an archive or checksum")
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "x:gz") as output:
        output.add(source, arcname="toolchain")
    digest = hashlib.sha256()
    with archive.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    with checksum.open("x", encoding="utf-8") as stream:
        stream.write(f"{digest.hexdigest()}  {archive.name}\n")
    print(f"Created archive and SHA-256 checksum: {archive}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--archive", type=Path, help="Optional .tar.gz and checksum, outside the SDK")
    args = parser.parse_args()
    build(args.output.resolve())
    if args.archive:
        archive_bundle(args.output, args.archive)
