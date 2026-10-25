"""Experimental, opt-in SDK download and installation (never run on the GUI thread)."""

from __future__ import annotations

import argparse
import hashlib
from http.client import HTTPException
from ipaddress import ip_address, ip_network
import json
import os
import platform
from pathlib import Path, PurePosixPath
import re
import sys
import tarfile
import tempfile
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .private_toolchain import PrivateSDK, user_toolchains_root


MAX_ARCHIVE_SIZE = 1024**3
MAX_EXTRACTED_SIZE = 4 * 1024**3
_TEST_NETWORKS = tuple(ip_network(value) for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))


class SDKInstallCancelled(InterruptedError):
    """Cooperative cancellation, distinct from network or filesystem failures."""


def _check_cancel(cancel_requested):
    if cancel_requested is not None and cancel_requested():
        raise SDKInstallCancelled("SDK installation cancelled")


def _check_url(url: str, allow_local_http: bool) -> None:
    parsed = urlsplit(url)
    local = parsed.hostname == "localhost"
    try:
        address = ip_address(parsed.hostname or "")
        local = address.is_loopback or any(address in network for network in _TEST_NETWORKS)
    except ValueError:
        pass  # Do not resolve arbitrary DNS names for the HTTP test exception.
    if (not parsed.hostname or parsed.username or parsed.password or parsed.fragment or
            not (parsed.scheme == "https" or (parsed.scheme == "http" and allow_local_http and local))):
        raise ValueError("Use HTTPS; --allow-local-http permits only trusted loopback or private IPv4 test servers")


class _Redirects(HTTPRedirectHandler):
    def __init__(self, allow_local_http):
        self.allow_local_http = allow_local_http

    def redirect_request(self, request, response, code, message, headers, new_url):
        _check_url(new_url, self.allow_local_http)
        return super().redirect_request(request, response, code, message, headers, new_url)


def _open(url, allow_local_http):
    _check_url(url, allow_local_http)
    opener = build_opener(_Redirects(allow_local_http))
    return opener.open(Request(url, headers={"User-Agent": "FPGALab-SDK/1"}), timeout=30)


def read_catalog(url: str, *, allow_local_http=False) -> tuple[dict, ...]:
    """Read a bounded versioned catalog; entries select immutable SDK identities."""
    with _open(url, allow_local_http) as response:
        payload = response.read(1024 * 1024 + 1)
        base_url = response.geturl()
    if len(payload) > 1024 * 1024:
        raise ValueError("SDK catalog exceeds size limit")
    data = json.loads(payload)
    if not isinstance(data, dict) or type(data.get("format")) is not int or data["format"] != 1:
        raise ValueError("Unsupported SDK catalog format")
    entries = data.get("sdks")
    if not isinstance(entries, list) or not entries:
        raise ValueError("SDK catalog must contain a nonempty sdks list")
    validated, identities = [], set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Invalid SDK catalog entry")
        sdk_id, platform = entry.get("id"), entry.get("platform")
        if (not isinstance(sdk_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,127}", sdk_id) or
                not isinstance(platform, str) or not platform or sdk_id in identities or
                type(entry.get("size")) is not int or not 0 < entry["size"] <= MAX_ARCHIVE_SIZE or
                not isinstance(entry.get("sha256"), str) or
                not re.fullmatch(r"[a-f0-9]{64}", entry["sha256"]) or
                not isinstance(entry.get("url"), str) or not entry["url"]):
            raise ValueError("Invalid or duplicate SDK catalog entry")
        archive_url = urljoin(base_url, entry["url"])
        _check_url(archive_url, allow_local_http)
        identities.add(sdk_id)
        validated.append({**entry, "url": archive_url})
    return tuple(validated)


def _extract(archive: Path, stage: Path, cancel_requested=None) -> Path:
    if not hasattr(tarfile, "data_filter"):
        raise ValueError("Safe SDK extraction requires an updated Python with tarfile.data_filter")
    root = stage / "toolchain"
    root.mkdir()
    with tarfile.open(archive, "r:gz") as source:
        count, total = 0, 0
        for member in source:
            _check_cancel(cancel_requested)
            count += 1
            total += member.size
            path = PurePosixPath(member.name)
            if (count > 200_000 or member.size < 0 or total > MAX_EXTRACTED_SIZE or
                    path.is_absolute() or ".." in path.parts or not path.parts or
                    path.parts[0] != "toolchain" or
                    not (member.isfile() or member.isdir() or member.issym() or member.islnk())):
                raise ValueError("Unsafe SDK archive member or extraction limit exceeded")
            if (not (stage / member.name).resolve().is_relative_to(root) or
                    (len(path.parts) == 1 and not member.isdir())):
                raise ValueError("SDK member escapes its root")
            if member.issym() or member.islnk():
                link = Path(member.linkname)
                base = (stage / member.name).parent if member.issym() else stage
                if link.is_absolute() or not (base / link).resolve().is_relative_to(root):
                    raise ValueError("SDK archive link escapes its root")
            source.extract(member, stage, filter="data")
    for path in root.rglob("*"):
        _check_cancel(cancel_requested)
        if path.is_symlink() and (os.path.isabs(os.readlink(path)) or
                                  not path.resolve().is_relative_to(root) or not path.exists()):
            raise ValueError("SDK contains a non-portable symbolic link")
    return root


def install_sdk(catalog_url: str, sdk_id: str, *, destination: Path | None = None,
                allow_local_http=False, progress=None, cancel_requested=None,
                phase=None, expected_entry: dict | None = None) -> PrivateSDK:
    """Download, verify and publish a new SDK atomically; never overwrite an SDK.

    progress receives (downloaded_bytes, expected_bytes) and may raise to cancel.
    cancel_requested is checked between download blocks and archive members.
    phase receives a stage identifier; callbacks run on the caller's thread.
    expected_entry pins the catalog entry shown before GUI confirmation.
    Temporary files and the per-ID installation lock are cleaned on failure.
    """
    _check_cancel(cancel_requested)
    if phase:
        phase("catalog")
    entries = read_catalog(catalog_url, allow_local_http=allow_local_http)
    _check_cancel(cancel_requested)
    entry = next((item for item in entries if item["id"] == sdk_id), None)
    if entry is None:
        raise ValueError("SDK ID is not present in this catalog")
    if expected_entry is not None and entry != expected_entry:
        raise ValueError("SDK catalog changed; reload it before installing")
    # Only the controlled Linux SDK has a validated runtime today.
    if (sys.platform != "linux" or platform.machine().lower() not in ("x86_64", "amd64") or
            entry["platform"] != "linux-x86_64"):
        raise ValueError("SDK platform is not supported on this computer")
    parent = (destination if destination is not None else user_toolchains_root()).resolve()
    if any(character.isspace() for character in str(parent)):
        raise ValueError("This SDK does not support paths containing whitespace")
    parent.mkdir(parents=True, exist_ok=True)
    target = parent / sdk_id
    lock = parent / f".{sdk_id}.install.lock"
    # Exclusive creation also prevents two installers from publishing the same ID.
    with lock.open("x"):
        try:
            if target.exists() or target.is_symlink():
                raise FileExistsError("SDK ID is already installed; existing files were not changed")
            with tempfile.TemporaryDirectory(prefix=".sdk-install-", dir=parent) as temporary:
                stage = Path(temporary)
                archive = stage / "download.tar.gz"
                digest, received = hashlib.sha256(), 0
                if phase:
                    phase("download")
                with _open(entry["url"], allow_local_http) as response, archive.open("xb") as output:
                    read = getattr(response, "read1", response.read)
                    while True:
                        _check_cancel(cancel_requested)
                        block = read(1024 * 1024)
                        if not block:
                            break
                        received += len(block)
                        if received > entry["size"]:
                            raise ValueError("SDK download exceeds declared size")
                        digest.update(block)
                        output.write(block)
                        if progress:
                            progress(received, entry["size"])
                if received != entry["size"] or digest.hexdigest() != entry["sha256"]:
                    raise ValueError("SDK download size or SHA-256 does not match the catalog")
                _check_cancel(cancel_requested)
                if phase:
                    phase("extract")
                root = _extract(archive, stage, cancel_requested)
                _check_cancel(cancel_requested)
                if phase:
                    phase("validate")
                sdk = PrivateSDK.load(root, expected_id=sdk_id)
                for name in ("source-packages.json", "REDISTRIBUTION.txt"):
                    if not (root / name).is_file():
                        raise ValueError(f"SDK inventory is missing: {name}")
                receipt = {"format": 1, "sdk_id": sdk.sdk_id, "sha256": entry["sha256"],
                           "size": received, "catalog_url": catalog_url}
                (root / "installation.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
                if target.exists() or target.is_symlink():
                    raise FileExistsError("SDK destination appeared during installation")
                _check_cancel(cancel_requested)
                if phase:
                    phase("publish")
                root.rename(target)
            return PrivateSDK.load(target, expected_id=sdk_id)
        finally:
            lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", required=True, help="Trusted HTTPS catalog URL")
    parser.add_argument("--sdk-id", required=True)
    parser.add_argument("--allow-local-http", action="store_true", help="Trusted loopback/private IPv4 maintainer tests")
    args = parser.parse_args()
    last_percent = -10
    def progress(current, total):
        nonlocal last_percent
        percent = current * 100 // total
        if percent >= last_percent + 10 or current == total:
            print(f"Downloading SDK: {percent}% ({current}/{total} bytes)", flush=True)
            last_percent = percent
        if current == total:
            print("Verifying and installing SDK; please wait...", flush=True)
    try:
        sdk = install_sdk(args.catalog, args.sdk_id, allow_local_http=args.allow_local_http, progress=progress)
    except KeyboardInterrupt:
        parser.exit(130, "SDK installation cancelled.\n")
    except (OSError, ValueError, tarfile.TarError, HTTPException) as error:
        parser.exit(1, f"SDK installation failed: {error}\n")
    print(f"SDK installed: {sdk.root}")


if __name__ == "__main__":
    main()
