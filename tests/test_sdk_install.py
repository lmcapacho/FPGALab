"""SDK installation contracts using synthetic archives, never developer tools."""

from functools import partial
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import tarfile
import threading

import pytest

import fpga_lab.private_toolchain as private
import fpga_lab.sdk_install as installer


@pytest.fixture
def sdk_download(tmp_path, monkeypatch):
    monkeypatch.setattr(installer.sys, "platform", "linux")
    monkeypatch.setattr(installer.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(private, "host_glibc", lambda: (2, 39))
    server_root = tmp_path / "server"
    root = server_root / "toolchain"
    root.mkdir(parents=True)
    sdk_id = "ubuntu24.04-x86_64-sdk1"
    for name in ("verilator", "make", "g++", "python3", "perl", "sh"):
        path = root / "bin" / name
        path.parent.mkdir(exist_ok=True)
        path.write_text("synthetic executable; never run")
        path.chmod(0o755)
    for relative in ("rootfs/lib64/ld-linux-x86-64.so.2",
                     "rootfs/usr/share/verilator/include/verilated.h",
                     "source-packages.json", "REDISTRIBUTION.txt"):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic resource")
    (root / "toolchain.json").write_text(json.dumps({
        "format": 1, "status": "experimental-controlled-build", "platform": "linux-x86_64",
        "recipe": {"id": sdk_id}, "glibc": "glibc 2.39",
        "packages": {"verilator": "5.020", "make": "4.3", "g++": "13", "python3": "3.12", "perl": "5.38"},
    }))
    archive = server_root / "sdk.tar.gz"
    with tarfile.open(archive, "w:gz") as output:
        output.add(root, arcname="toolchain")
    entry = {"id": sdk_id, "platform": "linux-x86_64", "url": "sdk.tar.gz",
             "size": archive.stat().st_size, "sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}
    catalog = server_root / "catalog.json"
    catalog.write_text(json.dumps({"format": 1, "sdks": [entry]}))

    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(server_root)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/catalog.json", entry, archive, catalog
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_sdk_http_install_is_discoverable_immutable_and_cleans_failed_downloads(sdk_download, tmp_path):
    url, entry, archive, catalog = sdk_download
    destination = tmp_path / "installed"
    progress = []
    sdk = installer.install_sdk(url, entry["id"], destination=destination, allow_local_http=True,
                                progress=lambda current, total: progress.append((current, total)))
    assert sdk.root == destination / entry["id"]
    assert private.sdk_candidates(destination) == (sdk.root,)
    assert progress[-1] == (entry["size"], entry["size"])
    assert (sdk.root / "bin/g++").stat().st_mode & 0o111
    receipt = json.loads((sdk.root / "installation.json").read_text())
    assert receipt["sha256"] == entry["sha256"]
    with pytest.raises(FileExistsError):
        installer.install_sdk(url, entry["id"], destination=destination, allow_local_http=True)
    assert (sdk.root / "installation.json").exists()
    lock = destination / f".{entry['id']}.install.lock"
    lock.write_text("another installer")
    with pytest.raises(FileExistsError):
        installer.install_sdk(url, entry["id"], destination=destination, allow_local_http=True)
    assert lock.read_text() == "another installer"
    lock.unlink()

    for changes in ({"sha256": "0" * 64}, {"size": entry["size"] - 1}, {"size": entry["size"] + 1}):
        catalog.write_text(json.dumps({"format": 1, "sdks": [{**entry, **changes}]}))
        failed = tmp_path / "failed"
        with pytest.raises(ValueError, match="SHA-256|size"):
            installer.install_sdk(url, entry["id"], destination=failed, allow_local_http=True)
        assert list(failed.iterdir()) == []
    catalog.write_text(json.dumps({"format": 1, "sdks": [entry]}))
    def cancel(*args):
        raise InterruptedError("cancelled")
    with pytest.raises(InterruptedError):
        installer.install_sdk(url, entry["id"], destination=tmp_path / "cancelled",
                              allow_local_http=True, progress=cancel)
    assert list((tmp_path / "cancelled").iterdir()) == []


def test_sdk_catalog_transport_and_schema_are_checked(sdk_download, tmp_path):
    url, entry, archive, catalog = sdk_download
    with pytest.raises(ValueError, match="HTTPS"):
        installer.read_catalog(url)
    for invalid in ("http://example.com/sdk", "file:///tmp/sdk", "https://user:secret@example.com/sdk"):
        with pytest.raises(ValueError):
            installer._check_url(invalid, True)
    for entries in ([entry, entry], [{**entry, "id": "../escape"}], [{**entry, "size": True}],
                    [{**entry, "url": "http://example.com/sdk"}]):
        catalog.write_text(json.dumps({"format": 1, "sdks": entries}))
        with pytest.raises(ValueError):
            installer.read_catalog(url, allow_local_http=True)
    catalog.write_text(json.dumps({"format": 1, "sdks": [{**entry, "platform": "windows-x86_64"}]}))
    with pytest.raises(ValueError, match="platform"):
        installer.install_sdk(url, entry["id"], destination=tmp_path / "never-created", allow_local_http=True)
    assert not (tmp_path / "never-created").exists()


def test_sdk_archive_rejects_escape_links_and_incomplete_trees(sdk_download, tmp_path):
    url, entry, archive, catalog = sdk_download
    for index, (name, link) in enumerate((("../escaped", None), ("toolchain/../../escaped", None),
                                         ("toolchain/link", "../../escaped"), ("toolchain", "."),
                                         ("toolchain/readme", None))):
        with tarfile.open(archive, "w:gz") as output:
            member = tarfile.TarInfo(name)
            if link is not None:
                member.type = tarfile.SYMTYPE
                member.linkname = link
                output.addfile(member)
            else:
                member.size = 1
                output.addfile(member, io.BytesIO(b"x"))
        bad = {**entry, "size": archive.stat().st_size,
               "sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}
        catalog.write_text(json.dumps({"format": 1, "sdks": [bad]}))
        target = tmp_path / f"unsafe-{index}"
        with pytest.raises(ValueError, match="SDK"):
            installer.install_sdk(url, entry["id"], destination=target, allow_local_http=True)
        assert list(target.iterdir()) == []
    assert not (tmp_path / "escaped").exists()
