#!/usr/bin/env python3
"""Serve the browser shell and only the prepared portion of a local installation."""
import argparse
import errno
import json
import mimetypes
import os
import re
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tools.shell_files import license_paths, runtime_paths
from tools.bonus_files import BONUS_FILES
from urllib.parse import unquote, urlsplit
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
PUBLIC = set(runtime_paths() + license_paths()) | {"", "engine/", "local-status.json"}
ART_FILES = {"background.webp","roc.webp","tft.webp","border.png","fill.png","icon-192.png","icon-512.png","font.ttf","button.webp"}

COMPACT_ZIP = "Warcraft-III-1.31.1-ruRU-compact.zip"

class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_HEAD(self):
        self.respond(False)

    def do_GET(self):
        self.respond(True)

    def respond(self, body):
        path = unquote(urlsplit(self.path).path).removeprefix("/")
        if path == "engine":
            self.send_response(301)
            self.send_header("Location", "engine/")
            self.end_headers()
            return
        if path == "engine/gamedata/paths.index.json" and not self.server.pack_only:
            root = ROOT / "local/gamedata"
            if not root.is_dir():
                return self.send_error(404)
            # A prepared mirror is installed by an atomic rename.
            bonus = ROOT / "local/bonus"
            stamp = (root.stat().st_ino, bonus.stat().st_ino if bonus.is_dir() else None)
            if getattr(self.server, "index_stamp", None) != stamp:
                names = {(Path(base)/name).relative_to(root).as_posix()
                         for base, _, files in os.walk(root) for name in files}
                names.update(n.removeprefix('gamedata/') for n in BONUS_FILES if (bonus / n).is_file())
                self.server.path_index = json.dumps(sorted(names), separators=(",", ":")).encode()
                self.server.index_stamp = stamp
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(self.server.path_index)))
            self.end_headers()
            if body:
                self.wfile.write(self.server.path_index)
            return
        if path == "local-status.json":
            maps = ROOT / "local/gamedata/maps.index.txt"
            ready = maps.is_file() and maps.stat().st_size > 0
            status = {"application": "warcraft3-web", "ready": ready and not self.server.pack_only}
            if (ROOT/"local/distribution/manifest.json").is_file():
                status["distribution"] = "distribution/manifest.json"
            data = json.dumps(status).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if body:
                self.wfile.write(data)
            return
        _, _, tail = path.partition("/")
        download = path == "download/" + COMPACT_ZIP
        if path in PUBLIC:
            base, name = ROOT, ("engine/index.html" if path == "engine/" else path or "index.html")
        elif download:
            base, name = ROOT / "local", COMPACT_ZIP
        elif path.startswith("distribution/") and (tail == "manifest.json" or
                re.fullmatch(r"[0-9a-f]{64}\.bin",tail) or tail in {"presentation/"+f for f in ART_FILES}):
            base, name = ROOT/"local/distribution", tail
        elif path.startswith("presentation/") and tail in ART_FILES:
            base, name = ROOT/"local/compact/presentation", tail
        elif path.startswith(("engine/gamedata/", "engine/movies/")) and not self.server.pack_only:
            base, name = ROOT / "local", path[len("engine/"):]
            if name in BONUS_FILES and (base / "bonus" / name).is_file():
                base = base / "bonus"
            if any(part.startswith(".") for part in name.split("/")):
                return self.send_error(404)
        else:
            return self.send_error(404)
        base = base.resolve()
        target = (base / name).resolve()
        if base not in target.parents or not target.is_file():
            return self.send_error(404)
        size = target.stat().st_size
        mime = ("application/octet-stream" if name.startswith("gamedata/") else
                mimetypes.guess_type(target.name)[0] or "application/octet-stream")
        start, end, status = 0, size-1, 200
        partial = self.headers.get("Range")
        supports_range = download or name.startswith("movies/")
        if partial and supports_range:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", partial)
            if not match or not any(match.groups()):
                return self.send_error(416)
            a, b = match.groups()
            start = int(a) if a else max(0, size-int(b))
            end = min(int(b), size-1) if a and b else size-1
            if not 0 <= start <= end < size:
                return self.send_error(416)
            status = 206
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(end-start+1))
        self.send_header("Cache-Control", "no-cache")
        if download:
            self.send_header("Content-Disposition", f'attachment; filename="{COMPACT_ZIP}"')
        if supports_range:
            self.send_header("Accept-Ranges", "bytes")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if not body:
            return
        if base in {(ROOT / "local").resolve(), (ROOT / "local/bonus").resolve()} and self.server.trace and not download:
            with self.server.trace_lock:
                if name not in self.server.seen:
                    with self.server.trace.open("a", encoding="utf-8") as stream:
                        print(name, file=stream)
                    self.server.seen.add(name)
        try:
            with target.open("rb") as stream:
                stream.seek(start)
                remaining = end-start+1
                while remaining:
                    data = stream.read(min(remaining, 256*1024))
                    if not data:
                        break
                    self.wfile.write(data)
                    remaining -= len(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8883)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--open", action="store_true")
    parser.add_argument("--pack-only", action="store_true", help="serve the compact distribution and shell")
    parser.add_argument("--trace", type=Path, help="record each served local asset for a measured test pack")
    args = parser.parse_args()
    url = f"http://{args.host}:{args.port}/"
    try:
        server = Server((args.host, args.port), Handler)
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE:
            try:
                with urlopen(url + "local-status.json", timeout=2) as response:
                    if json.load(response).get("application") == "warcraft3-web":
                        print(url, flush=True)
                        if args.open:
                            webbrowser.open(url)
                        return
            except (OSError, ValueError):
                pass
        parser.exit(1, f"{exc}\n{url}\n")
    server.trace, server.trace_lock, server.seen = args.trace, threading.Lock(), set()
    if args.trace:
        args.trace.parent.mkdir(parents=True, exist_ok=True)
    server.pack_only = args.pack_only
    print(f"http://{args.host}:{args.port}/", flush=True)
    if args.open:
        webbrowser.open(url)
    with server:
        server.serve_forever()

if __name__ == "__main__":
    main()
