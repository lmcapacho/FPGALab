#!/usr/bin/env python3
"""Serve one trusted local SDK and a generated catalog on loopback for testing."""

import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import shutil


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--sdk-id", required=True)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,127}", args.sdk_id):
        parser.error("Invalid SDK ID")
    archive = args.archive.resolve()
    digest = hashlib.sha256()
    with archive.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    size = archive.stat().st_size
    catalog = json.dumps({"format": 1, "sdks": [{
        "id": args.sdk_id, "platform": "linux-x86_64", "url": "sdk.tar.gz",
        "size": size, "sha256": digest.hexdigest(),
    }]}).encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            # Never expose directory listings, the checkout, or arbitrary local files.
            if self.path not in ("/catalog.json", "/sdk.tar.gz"):
                self.send_error(404)
                return
            is_catalog = self.path == "/catalog.json"
            self.send_response(200)
            self.send_header("Content-Type", "application/json" if is_catalog else "application/gzip")
            self.send_header("Content-Length", str(len(catalog) if is_catalog else size))
            self.end_headers()
            try:
                if is_catalog:
                    self.wfile.write(catalog)
                else:
                    with archive.open("rb") as stream:
                        shutil.copyfileobj(stream, self.wfile)
            except (BrokenPipeError, ConnectionResetError):
                pass

    with ThreadingHTTPServer(("127.0.0.1", args.port), Handler) as server:
        print("Experimental local test only: use a trusted, unchanged archive.", flush=True)
        print(f"Catalog: http://127.0.0.1:{server.server_port}/catalog.json", flush=True)
        print(f"SDK: {args.sdk_id}; bytes: {size}; SHA-256: {digest.hexdigest()}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
