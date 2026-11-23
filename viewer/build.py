"""Build the pinned browser engine into its own cache. No game files enter the build."""
import argparse
import shutil
import subprocess
from pathlib import Path
from encoding import patch_text_decoders

PIN = 'e0530078bb937e55b479c4d0286266ab955514f4'
HERE = Path(__file__).resolve().parent
CACHE = Path.home() / 'Library/Caches/warcraft3-original-web/openwar3'

def run(args, cwd):
    subprocess.run(args, cwd=cwd, check=True)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, default=CACHE)
    args = parser.parse_args()
    cache = args.cache.expanduser().resolve()
    cache.mkdir(parents=True, exist_ok=True)
    src = cache / 'source'
    if not src.exists():
        run(['git', 'init', str(src)], cache)
        run(['git', 'fetch', '--depth=1', 'https://github.com/elevchyt/openwar3.git', PIN], src)
        run(['git', 'checkout', '--detach', 'FETCH_HEAD'], src)
    if subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=src, text=True).strip() != PIN:
        raise SystemExit('The build cache contains a different OpenWar3 revision.')
    for name in ('package.json', 'package-lock.json'):
        shutil.copyfile(HERE / name, cache / name)
    run(['npm', 'ci', '--no-audit', '--no-fund'], cache)
    deps = cache / 'node_modules'
    for name, version in [('mdx-m3-viewer', '5.12.0'), ('fengari', '0.1.5')]:
        patch = src / 'patches' / f'{name}@{version}.patch'
        run(['git', 'apply', '--unsafe-paths', '--ignore-space-change', '--ignore-whitespace', '--whitespace=nowarn', str(patch)], deps / name)
    # An async asset solver returns a URL promise for model events such as sounds.
    generic_loader = deps / 'mdx-m3-viewer/dist/cjs/viewer/viewer.js'
    source = generic_loader.read_text()
    signature = 'async loadGeneric(fetchUrl, dataType, callback) {'
    if source.count(signature) != 1:
        raise SystemExit('The generic asset loader changed')
    adapter = """
        fetchUrl = await fetchUrl;
        if (ArrayBuffer.isView(fetchUrl) || fetchUrl instanceof ArrayBuffer) {
            const url = URL.createObjectURL(new Blob([fetchUrl]));
            try { return await this.loadGeneric(url, dataType, callback); }
            finally { URL.revokeObjectURL(url); }
        }
    """
    generic_loader.write_text(source.replace(signature, signature + adapter))
    scoped = deps / '@openwar3'
    scoped.mkdir(exist_ok=True)
    (scoped / 'ui').symlink_to(src / 'packages' / 'ui', target_is_directory=True)
    if not (src / 'node_modules').exists():
        (src / 'node_modules').symlink_to(deps, target_is_directory=True)
    shutil.copyfile(HERE / 'browser.config.mjs', src / 'browser.config.mjs')
    run([str(deps / '.bin/vite'), 'build', '--config', 'browser.config.mjs'], src)
    dist = cache / 'dist'
    patch_text_decoders(dist)
    for name in ('fonts', 'favicon.ico', 'icon-192.png', 'icon-512.png', 'apple-touch-icon.png'):
        source = src / 'public' / name
        if source.is_dir():
            shutil.copytree(source, dist / name, dirs_exist_ok=True)
        else:
            shutil.copyfile(source, dist / name)
    shutil.copyfile(src / 'LICENSE', dist / 'OpenWar3-LICENSE.txt')
    print(dist)

if __name__ == '__main__':
    main()
