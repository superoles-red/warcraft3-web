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
from urllib.parse import unquote, urlsplit
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
PUBLIC = {"", "index.html", "app.js", "style.css", "sw.js", "pack.js", "manifest.webmanifest", "icon.png", "lib/fflate-0.8.2.js"}
ENGINE = {"", "index.html", "wc3-input.js", "pack-runtime.js", "openwarcraft3.js", "openwarcraft3.wasm",
          "openwarcraft3.data", "version.json", "LICENSE", "NOTICE.md"}

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
        if path == "engine/gamedata/paths.index.json":
            root = ROOT / "local/gamedata"
            if not root.is_dir():
                return self.send_error(404)
            # A prepared mirror is installed by an atomic rename.
            stamp = root.stat().st_ino
            if getattr(self.server, "index_stamp", None) != stamp:
                names = sorted((Path(base)/name).relative_to(root).as_posix()
                               for base, _, files in os.walk(root) for name in files)
                self.server.path_index = json.dumps(names, separators=(",", ":")).encode()
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
            data = json.dumps({"application": "warcraft3-web", "ready": ready}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if body:
                self.wfile.write(data)
            return
        group, _, tail = path.partition("/")
        if path in PUBLIC:
            base, name = ROOT, path or "index.html"
        elif group == "engine" and tail in ENGINE:
            base, name = ROOT / "engine", tail or "index.html"
        elif path.startswith(("engine/gamedata/", "engine/movies/")):
            base, name = ROOT / "local", path[len("engine/"):]
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
        if partial and name.startswith("movies/"):
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
        if name.startswith("movies/"):
            self.send_header("Accept-Ranges", "bytes")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if not body:
            return
        if base == (ROOT / "local").resolve() and self.server.trace:
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
    parser.add_argument("--trace", type=Path, help="record each served local asset for a measured test pack")
    args = parser.parse_args()
    url = f"http://127.0.0.1:{args.port}/"
    try:
        server = Server((args.host, args.port), Handler)
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE and args.open:
            try:
                with urlopen(url + "local-status.json", timeout=2) as response:
                    if json.load(response).get("application") == "warcraft3-web":
                        webbrowser.open(url)
                        return
            except (OSError, ValueError):
                pass
        parser.exit(1, f"{exc}\n{url}\n")
    server.trace, server.trace_lock, server.seen = args.trace, threading.Lock(), set()
    if args.trace:
        args.trace.parent.mkdir(parents=True, exist_ok=True)
    print(url, flush=True)
    if args.open:
        webbrowser.open(url)
    with server:
        server.serve_forever()

if __name__ == "__main__":
    main()
