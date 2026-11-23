"""Files belonging to the web shell, independent of a Warcraft installation."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOOT = (
    "index.html", "app.js", "pack.js", "sw.js", "manifest.webmanifest",
    "loading.js", "loading.css", "shell-release.js",
)
ENGINE = (
    "index.html", "wc3-input.js", "pack-runtime.js", "openwarcraft3.js",
    "openwarcraft3.wasm", "openwarcraft3.data", "version.json",
)


def runtime_paths():
    modules = sorted((ROOT / "engine").glob("*.mjs"))
    libraries = sorted(path for path in (ROOT / "lib").rglob("*")
                       if path.is_file() and path.suffix in (".js", ".mjs"))
    return [*BOOT, *("engine/" + name for name in ENGINE),
            *(path.relative_to(ROOT).as_posix() for path in modules + libraries)]


def license_paths():
    notices = sorted(path.relative_to(ROOT).as_posix() for path in (ROOT / "lib").rglob("*")
                     if path.is_file() and path.name.startswith(("LICENSE", "NOTICE", "THIRD_PARTY_NOTICES")))
    return ["engine/NOTICE.md", "engine/LICENSE", "engine/LICENSE-OpenRealm", *notices]
