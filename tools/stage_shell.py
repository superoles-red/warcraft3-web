#!/usr/bin/env python3
"""Compute the offline cache revision and optionally stage the public shell."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

from shell_files import ROOT, license_paths, runtime_paths

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path)
args = parser.parse_args()

paths = runtime_paths()
digest = hashlib.sha256()
for name in paths:
    if name != "shell-release.js":
        digest.update(name.encode() + b"\0" + (ROOT / name).read_bytes())

revision = digest.hexdigest()[:16]
cache = [name for name in paths if name not in ("sw.js", "shell-release.js")]
record = json.dumps({"revision": revision, "files": cache}, separators=(",", ":"))
(ROOT / "shell-release.js").write_text(f"self.WC3_SHELL = {record};\n")
if args.output:
    for name in [*paths, ".nojekyll", "local-status.json", *license_paths()]:
        destination = args.output / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
print(revision)
