#!/usr/bin/env python3
"""Build a frozen Ubuntu SDK and test it in a clean, offline runtime container."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


HERE = Path(__file__).resolve().parent


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
    metadata.update(status="experimental-controlled-build", recipe=recipe)
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    # Relocate before generating Makefiles, which contain absolute paths.
    relocated = Path("/out/relocated-sdk")
    sdk.rename(relocated)
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
    return [build, [*run, image, "--export"],
            [*run, recipe["image"], "/out/relocated-sdk/bin/python3", "/out/probe.py",
             "--run", "--sandboxed", "--work-dir", "/out/probe"],
            [*run, "--entrypoint", "python3", image,
             "/src/packaging/linux_toolchain/container_build.py", "--archive"]]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="New output directory outside the repository")
    parser.add_argument("--export", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--archive", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.export:
        export_sdk()
        return
    if args.archive:
        import build
        build.archive_bundle(Path("/out/relocated-sdk"), Path("/out/fpgalab-linux-sdk.tar.gz"))
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
        ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
        shutil.copytree(repository / "fpga_lab", context / "fpga_lab", ignore=ignore)
        shutil.copytree(HERE, context / "packaging/linux_toolchain", ignore=ignore)
        for command in commands(output, recipe, context):
            subprocess.run(command, check=True)
    (output / "validation.json").write_text(json.dumps({
        "recipe": recipe, "checks": ["relocation", "offline-clean-ubuntu", "native-abi", "repeated-make"],
        "scope": "SDK only; graphical application and other distributions are not qualified",
    }, indent=2) + "\n", encoding="utf-8")
    print(f"PASS: controlled SDK and checksum in {output}")


if __name__ == "__main__":
    main()
