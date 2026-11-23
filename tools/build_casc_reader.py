#!/usr/bin/env python3
"""Compile the local Warcraft III archive reader from a pinned CascLib checkout."""
import argparse
import concurrent.futures
import os
from pathlib import Path
import re
import subprocess
import sys

REVISION = '6b889ec8f421cbc9baccec296c582362ab917887'
SOURCE = Path(__file__).with_name('casc_reader.cpp').resolve()


def build(cache):
    cache = cache.resolve()
    cache.mkdir(parents=True, exist_ok=True)
    source = cache / 'CascLib'
    if not source.exists():
        subprocess.run(['git', 'init', '-q', str(source)], check=True)
        subprocess.run(['git', '-C', str(source), 'fetch', '--depth=1',
                        'https://github.com/ladislav-zezula/CascLib.git', REVISION], check=True)
        subprocess.run(['git', '-C', str(source), 'checkout', '-q', '--detach', 'FETCH_HEAD'], check=True)
    actual = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if actual != REVISION:
        raise SystemExit(f'Expected CascLib {REVISION}, found {actual} in {source}. Use a fresh --cache directory.')
    build_dir = cache / ('casc-build-' + REVISION[:12])
    build_dir.mkdir(exist_ok=True)
    cpp_files = [source / f.replace('\\', '/') for f in
                 re.findall(r'#include "([^"]+)"', (source / 'sources-cpp.cpp').read_text())]
    files = cpp_files + [source / 'src/jenkins/lookup3.c', SOURCE]
    includes = ['-DCASC_USE_SYSTEM_ZLIB', '-I' + str(source / 'src'), '-O2', '-DNDEBUG']

    def compile_one(path):
        obj = build_dir / (path.name + '.o')
        if not obj.is_file() or obj.stat().st_mtime < path.stat().st_mtime:
            cmd = ([os.environ.get('CC', 'cc')] if path.suffix == '.c'
                   else [os.environ.get('CXX', 'c++'), '-std=c++17'])
            subprocess.run(cmd + includes + ['-c', str(path), '-o', str(obj)], check=True)
        return obj

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(6, os.cpu_count() or 1)) as executor:
        objects = list(executor.map(compile_one, files))
    binary = build_dir / 'casc_reader'
    if not binary.is_file() or binary.stat().st_mtime < max(p.stat().st_mtime for p in objects):
        link = [os.environ.get('CXX', 'c++'), *map(str, objects), '-lz', '-pthread']
        if sys.platform == 'darwin':
            link += ['-framework', 'Carbon']
        subprocess.run(link + ['-o', str(binary)], check=True)
    return binary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, required=True)
    print(build(parser.parse_args().cache))
