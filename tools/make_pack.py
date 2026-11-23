#!/usr/bin/env python3
"""Create a private, standard ZIP for the browser from a full mirror or a playtest trace."""
import argparse
import json
import hashlib
import os
import tempfile
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED, ZIP_STORED
from bonus_files import BONUS_FILES

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("output", type=Path)
parser.add_argument("--local", type=Path, default=Path(__file__).resolve().parents[1] / "local")
parser.add_argument("--trace", type=Path, help="include only files observed during this playtest")
parser.add_argument("--start-map", help="launch this original map directly when importing the package")
parser.add_argument("--compact", action="store_true", help="pack optimized game audio, movies and original loading artwork")
args = parser.parse_args()
root = args.local.resolve()
maps = root / "gamedata/maps.index.txt"
if not maps.is_file():
    parser.error("prepare the gamedata mirror first")
if args.trace:
    names = set(args.trace.read_text().splitlines())
    names.update(("gamedata/b64.index.txt", "gamedata/maps.index.txt"))
else:
    names = {p.relative_to(root).as_posix() for d in ("gamedata", "movies")
             for p in (root / d).rglob("*") if p.is_file()}
names = {n for n in names if n.startswith(("gamedata/", "movies/"))
         and all(p not in ("", ".", "..") and not p.startswith(".") for p in n.split("/"))}
if not any(n.endswith((".w3m", ".w3x")) for n in names):
    parser.error("no playable maps present in this selection")
overrides = {}
bonus = root / 'bonus'
bonus_maps = {n for n in BONUS_FILES if n.endswith('.w3m')}
if bonus.exists() and (not args.trace or names & bonus_maps):
    missing = sorted(n for n in BONUS_FILES if not (bonus / n).is_file())
    if missing:
        parser.error('incomplete bonus campaign: ' + ', '.join(missing))
    names.update(BONUS_FILES)
    overrides.update({n: bonus / n for n in BONUS_FILES})
if args.start_map and "gamedata/" + args.start_map not in names:
    parser.error("start map is missing from the package")
art = set()
if args.compact:
    audio = root / "audio-compact"
    report = json.loads((audio / "audio-report.json").read_text())
    if report["format"] != "w3ao1":
        parser.error("unsupported game audio format")
    details = report["files"]
    for name in names:
        if name.startswith("gamedata/") and (name.endswith(".wav") or
                (name.startswith("gamedata/sound/dialogue/") and name.endswith(".mp3"))):
            rel = name[len("gamedata/"):]
            entry = details[rel]
            if entry["converted"]:
                if hashlib.sha256((root / name).read_bytes()).hexdigest() != entry["sourceSha256"]:
                    parser.error("audio overlay is stale for " + name)
                overrides[name] = audio / name
        if name.startswith("movies/") and name.endswith("_native.webm"):
            overrides[name] = root / "compact" / name.replace("_native.webm", "_640.webm")
    if "movies/sizes.json" in names:
        overrides["movies/sizes.json"] = root / "compact/movies/sizes.json"
    if not args.trace and sum(n.endswith("_native.webm") for n in overrides) != 9:
        parser.error("expected all nine campaign movies")
    for path in (root/"compact/presentation").glob("*"):
        if path.is_file():
            name = 'presentation/' + path.name
            overrides[name] = path
            art.add(name)
    if "presentation/background.webp" not in art:
        parser.error("prepare the original loading screen first")
    names.update(art)
args.output.parent.mkdir(parents=True, exist_ok=True)
with tempfile.NamedTemporaryFile(dir=args.output.parent, delete=False) as temp:
    tmp = Path(temp.name)
try:
    with ZipFile(tmp, "w", ZIP_DEFLATED, compresslevel=6, allowZip64=False) as out:
        manifest = {"format": 1, "profile": "trace" if args.trace else "full", "startMap": args.start_map}
        if args.compact:
            manifest["audioFormat"] = "w3ao1"
        out.writestr("warcraft3-pack.json", json.dumps(manifest))
        for name in sorted(names):
            src = overrides.get(name, root / name).resolve(strict=True)
            if root not in src.parents:
                raise ValueError(f"outside local tree: {name}")
            if args.trace and name in ("gamedata/maps.index.txt", "gamedata/b64.index.txt"):
                suffix = ".b64" if "b64." in name else ""
                lines = [line for line in src.read_text().splitlines() if "gamedata/" + line + suffix in names]
                out.writestr(name, "".join(line + "\n" for line in lines))
            else:
                method = ZIP_STORED if name in overrides or src.suffix in (".webm", ".mp3", ".ogg", ".flac") else ZIP_DEFLATED
                out.write(src, name, compress_type=method)
    os.replace(tmp, args.output)
finally:
    tmp.unlink(missing_ok=True)
print(f"{len(names)} files, {args.output.stat().st_size:,} bytes → {args.output}")
