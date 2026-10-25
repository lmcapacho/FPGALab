#!/usr/bin/env python3
"""Build a frozen Ubuntu SDK and test it in a clean, offline runtime container."""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


HERE = Path(__file__).resolve().parent
CONTEXT_FILES = ("LICENSE", "NOTICE", "AUTHORS.md", "AI_USAGE.md", "pyproject.toml")


def load_tool(name):
    spec = importlib.util.spec_from_file_location(f"fpgalab_sdk_{name}", HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_tools():
    return load_tool("sources")


def prepare_context(repository, context):
    """Capture actual build inputs, including dirty working-tree changes, never Git internals."""
    sources = source_tools()
    excluded = shutil.ignore_patterns("__pycache__", "*.pyc", ".env", ".env.*", ".git", ".venv", "venv",
                                     "*.so", "*.dll", "*.dylib")
    def ignore(directory, names):
        ignored = excluded(directory, names)
        for name in set(names) - set(ignored):
            if (Path(directory) / name).is_symlink():
                raise ValueError(f"Build input symlinks must be resolved explicitly: {Path(directory) / name}")
        return ignored
    shutil.copytree(repository / "fpga_lab", context / "fpga_lab", ignore=ignore)
    shutil.copytree(repository / "packaging/linux_toolchain", context / "packaging/linux_toolchain", ignore=ignore)
    for name in CONTEXT_FILES:
        shutil.copy2(repository / name, context / name)
    tracked = {}
    try:
        revision = subprocess.run(["git", "-C", str(repository), "rev-parse", "HEAD"],
                                  capture_output=True, text=True, check=False)
        status = subprocess.run(["git", "-C", str(repository), "status", "--porcelain", "--untracked-files=all",
                                 "--", "fpga_lab", "packaging/linux_toolchain", *CONTEXT_FILES],
                                capture_output=True, text=True, check=False)
        if revision is not None and status is not None and revision.returncode == status.returncode == 0:
            tracked = {"revision": revision.stdout.strip(), "dirty": bool(status.stdout.strip())}
    except OSError:
        pass  # Exported source archives need not have Git installed or a .git directory.
    files = {path.relative_to(context).as_posix(): sources.sha256(path)
             for path in sorted(context.rglob("*")) if path.is_file()}
    (context / "provenance.json").write_text(json.dumps({
        "format": 1, "git": tracked or {"revision": None, "dirty": None}, "files": files,
    }, indent=2) + "\n", encoding="utf-8")


def load_recipe(path=HERE / "recipe.json"):
    recipe = json.loads(path.read_text(encoding="utf-8"))
    if (recipe.get("format") != 1 or
            not re.fullmatch(r"ubuntu:24\.04@sha256:[a-f0-9]{64}", recipe.get("image", "")) or
            not re.fullmatch(r"\d{8}T\d{6}Z", recipe.get("snapshot", "")) or
            not re.fullmatch(r"[a-z0-9._-]+", recipe.get("id", ""))):
        raise ValueError("Invalid frozen Ubuntu SDK recipe")
    return recipe


def export_sdk():
    # Runs inside the controlled image, never installs anything on the host.
    import build
    import probe
    recipe = load_recipe()
    sdk = Path("/out/sdk")
    build.build(sdk)
    metadata_path = sdk / "toolchain.json"
    metadata = json.loads(metadata_path.read_text())
    provenance = json.loads(Path("/src/provenance.json").read_text())
    metadata.update(status="experimental-controlled-build", recipe=recipe, build_provenance=provenance)
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    # Relocate before generating Makefiles, which contain absolute paths.
    relocated = Path("/out/relocated-sdk")
    sdk.rename(relocated)
    shutil.copy2("/src/LICENSE", relocated / "FPGALAB-LICENSE.txt")
    shutil.copy2("/src/NOTICE", relocated / "FPGALAB-NOTICE.txt")
    with (relocated / "REDISTRIBUTION.txt").open("a", encoding="utf-8") as stream:
        stream.write("FPGALab build/relocation adaptations: AGPL-3.0-or-later; see FPGALAB-LICENSE.txt.\n"
                     "Exact adaptations and package sources: separate fpgalab-linux-sdk-sources.tar.gz.\n"
                     "Collection/verification of sources is NOT legal approval or a durable public source offer.\n")
    probe.prepare(relocated, Path("/out/probe"))
    shutil.copy2(HERE / "probe.py", "/out/probe.py")


def commands(output, recipe, context=None):
    """Return inspectable Docker commands without executing them."""
    image = f"fpgalab-sdk:{recipe['id']}"
    user = f"{os.getuid()}:{os.getgid()}"
    mount = f"type=bind,src={output},dst=/out"
    build = ["docker", "build", "--platform", "linux/amd64", "--tag", image,
             "--file", str((context / "packaging/linux_toolchain" if context else HERE) / "Dockerfile"),
             "--build-arg", f"UBUNTU_IMAGE={recipe['image']}",
             "--build-arg", f"UBUNTU_SNAPSHOT={recipe['snapshot']}", str(context or HERE.parents[1])]
    run = ["docker", "run", "--rm", "--platform", "linux/amd64", "--network", "none",
           "--read-only", "--tmpfs", "/tmp:rw,exec", "--cap-drop", "ALL",
           "--security-opt", "no-new-privileges", "--user", user, "--mount", mount]
    # Only source collection needs networking; the model probe and final archiving stay offline.
    online = run.copy()
    online[online.index("--network") + 1] = "bridge"
    return [build, [*run, image, "--export"],
            [*run, recipe["image"], "/out/relocated-sdk/bin/python3", "/out/probe.py",
             "--run", "--sandboxed", "--work-dir", "/out/probe"],
            [*online, image, "--sources"],
            [*run, "--entrypoint", "python3", image,
             "/src/packaging/linux_toolchain/container_build.py", "--archive"]]


def archive_outputs(output):
    """Verify all source coverage before producing the source and binary companions."""
    build, sources = load_tool("build"), source_tools()
    sdk, source = output / "relocated-sdk", output / "sdk-sources"
    manifest = sources.verify_collection(sdk, source)
    archive = output / "fpgalab-linux-sdk-sources.tar.gz"
    checksum = sources.archive_sources(source, archive)
    metadata_path = sdk / "toolchain.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["source_bundle"] = {"file": archive.name, "sha256": checksum,
                               "manifest_sha256": sources.sha256(source / "source-manifest.json"),
                               "status": manifest["status"]}
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    build.archive_bundle(sdk, output / "fpgalab-linux-sdk.tar.gz")
    (output / "source-bundle.json").write_text(json.dumps({
        "format": 1, "sdk_id": metadata["recipe"]["id"], "legal_approval": False,
        "sdk": {"file": "fpgalab-linux-sdk.tar.gz", "sha256": sources.sha256(output / "fpgalab-linux-sdk.tar.gz")},
        "sources": metadata["source_bundle"], "source_versions": len(manifest["sources"]),
    }, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="New output directory outside the repository")
    parser.add_argument("--export", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--archive", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--sources", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.export:
        export_sdk()
        return
    if args.sources:
        sources = source_tools()
        sources.collect(Path("/out/relocated-sdk"), Path("/out/sdk-sources"), Path("/src"))
        return
    if args.archive:
        archive_outputs(Path("/out"))
        return
    if args.output is None:
        parser.error("--output is required")
    output = args.output.resolve()
    repository = HERE.parents[1]
    if output.exists() or output.is_relative_to(repository) or any(c.isspace() or c == "," for c in str(output)):
        parser.error("Use a new output directory outside the repository, without whitespace or commas")
    recipe = load_recipe()
    subprocess.run(["docker", "info"], check=True, stdout=subprocess.DEVNULL)
    output.mkdir(parents=True)
    # Send only required sources, not .git, virtualenvs, local secrets or caches,
    # including when Docker falls back to the legacy builder.
    with tempfile.TemporaryDirectory(prefix="fpgalab-sdk-context-") as directory:
        context = Path(directory)
        prepare_context(repository, context)
        for command in commands(output, recipe, context):
            subprocess.run(command, check=True)
    (output / "validation.json").write_text(json.dumps({
        "recipe": recipe, "checks": ["relocation", "offline-clean-ubuntu", "native-abi", "repeated-make",
                                      "exact-package-sources", "source-sha256", "adaptation-provenance"],
        "scope": "SDK and source collection only; NOT legal approval, GUI or other-distribution qualification",
    }, indent=2) + "\n", encoding="utf-8")
    print(f"PASS: controlled SDK, separate sources and checksums in {output}; legal review remains pending")


if __name__ == "__main__":
    main()
