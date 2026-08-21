"""GitHub Releases update discovery for FPGALab."""

from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass

from . import __version__

GITHUB_REPOSITORY = "lmcapacho/FPGALab"
RELEASES_URL = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/releases"
_VERSION_PATTERN = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-?rc(\d+))?$", re.IGNORECASE)


@dataclass(frozen=True)
class ReleaseInfo:
    """A published GitHub release suitable for update comparison."""

    version: str
    name: str
    url: str
    prerelease: bool


def parse_version(value: str) -> tuple[int, int, int, int, int] | None:
    """Return a comparable version key, with stable releases above their RCs."""
    match = _VERSION_PATTERN.fullmatch(value.strip())
    if match is None:
        return None
    major, minor, patch, release_candidate = match.groups()
    if release_candidate is None:
        return int(major), int(minor), int(patch), 1, 0
    return int(major), int(minor), int(patch), 0, int(release_candidate)


def normalized_version(value: str) -> str:
    """Remove only the optional Git tag prefix from a version string."""
    return value.strip().removeprefix("v").removeprefix("V")


def current_version() -> str:
    """Return the version embedded in the installed application package."""
    return __version__


def check_for_updates(
    installed_version: str | None = None, *, include_prereleases: bool | None = None, timeout: float = 4.0
) -> dict[str, object]:
    """Query GitHub Releases and return the latest compatible release metadata."""
    installed = normalized_version(installed_version or current_version())
    installed_key = parse_version(installed)
    if installed_key is None:
        return {"ok": False, "error": f"Unsupported installed version: {installed}"}
    if include_prereleases is None:
        include_prereleases = "rc" in installed.lower()

    request = urllib.request.Request(
        RELEASES_URL,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "FPGALab update checker"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            releases = json.loads(response.read().decode("utf-8"))
    except Exception as error:  # Network failures are reported to the caller.
        return {"ok": False, "error": str(error)}

    latest: ReleaseInfo | None = None
    latest_key: tuple[int, int, int, int, int] | None = None
    for release in releases:
        if release.get("draft") or (release.get("prerelease") and not include_prereleases):
            continue
        version = normalized_version(str(release.get("tag_name", "")))
        version_key = parse_version(version)
        if version_key is None or (latest_key is not None and version_key <= latest_key):
            continue
        latest_key = version_key
        latest = ReleaseInfo(
            version=version,
            name=str(release.get("name") or version),
            url=str(release.get("html_url") or f"https://github.com/{GITHUB_REPOSITORY}/releases"),
            prerelease=bool(release.get("prerelease")),
        )

    if latest is None or latest_key is None:
        return {"ok": False, "error": "No published release with a supported version was found."}
    return {
        "ok": True,
        "update_available": latest_key > installed_key,
        "current_version": installed,
        "latest_version": latest.version,
        "release_name": latest.name,
        "release_url": latest.url,
        "prerelease": latest.prerelease,
    }
