#!/usr/bin/env python3
"""Export a private flat web mirror of the local 1.31 CASC base and selected language."""
import argparse
import base64
import csv
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile

from build_casc_reader import build

BASE = 'war3.w3mod:'
TEXT_FORMATS = {'.txt', '.fdf', '.toc', '.slk', '.sylk', '.j', '.cfg', '.ai', '.wai', '.wts', '.srt', '.json', '.pld'}


def select_files(rows, locale):
    language = BASE + '_locales\\' + locale.lower() + '.w3mod:'
    selected = {}
    localized = {}
    for record in rows:
        original = record['path']
        name = original.lower()
        if record['local'] != '1' or not name.startswith(BASE):
            continue
        is_language = name.startswith(language)
        relative = name[len(language if is_language else BASE):].replace('\\', '/')
        if not relative or ':' in relative or relative.startswith('movies/'):
            continue
        path = PurePosixPath(relative)
        if path.is_absolute() or '..' in path.parts or any(c in relative for c in '\n\r\t'):
            raise ValueError(f'Unsafe resource path {original!r}')
        dest = localized if is_language else selected
        dest[relative] = original
    for check in ('ui/campaignstrings.txt', 'ui/framedef/globalstrings.fdf'):
        if check not in localized:
            raise ValueError(f'{locale} is missing {check} in this installation')
    selected.update(localized)
    for check in ('ui/framedef/framedef.toc', 'scripts/common.j', 'campaign/human01.w3m'):
        if check not in selected:
            raise ValueError(f'This preparation profile requires classic 1.31 CASC game data containing {check}')
    return selected


def file_aliases(tree):
    # Classic model and GUI paths can point at atlased/relocated CASC resources.
    # Preserve the original relative names without copying their payload again.
    manifest = tree / 'filealiases.json'
    aliases = []
    for row in json.loads(manifest.read_text(encoding='utf-8-sig')):
        paths = [PurePosixPath(row[key].replace('\\', '/').lower()) for key in ('src', 'dest')]
        if any(p.is_absolute() or '..' in p.parts for p in paths):
            raise ValueError('Invalid relative path in filealiases.json')
        alias, target = (tree / p for p in paths)
        if not alias.exists() and target.is_file():
            alias.parent.mkdir(parents=True, exist_ok=True)
            os.link(target, alias)
            aliases.append(paths[0].as_posix())
    return aliases


def write_indexes(tree, paths):
    sidecars = []
    for name in paths:
        file = tree / name
        if file.suffix not in TEXT_FORMATS:
            continue
        data = file.read_bytes()
        if b'\0' in data or data.isascii():
            continue
        try:
            data.decode('utf-8')
        except UnicodeDecodeError:
            continue
        file.with_name(file.name + '.b64').write_bytes(base64.b64encode(data))
        sidecars.append(name)
    (tree / 'b64.index.txt').write_text(''.join(p + '\n' for p in sorted(sidecars)), encoding='utf8')
    maps = sorted(p for p in paths if p.startswith('maps/') and p.endswith(('.w3m', '.w3x')))
    (tree / 'maps.index.txt').write_text(''.join(p + '\n' for p in maps), encoding='utf8')
    return len(sidecars), len(maps)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('install', type=Path, help='Local installation containing .build.info and Data/')
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1] / 'local/gamedata',
                        help='New private output directory')
    parser.add_argument('--locale', default='ruru', help='Installed locale, default ruRU')
    parser.add_argument('--cache', type=Path, default=Path.home() / '.cache/warcraft3-original-web',
                        help='CascLib compiler and source cache; not served')
    parser.add_argument('--reader', type=Path, help='Use an existing build of tools/casc_reader.cpp')
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists():
        raise SystemExit(f'{out} already exists. Choose a new --output directory for a fresh export.')
    if not re.fullmatch('[A-Za-z]{4}', args.locale):
        raise SystemExit('Expected a four-letter Warcraft locale code.')
    cache = args.cache.resolve()
    cache.mkdir(parents=True, exist_ok=True)
    if not (args.install / '.build.info').is_file():
        raise SystemExit('The input directory must contain .build.info')
    reader = str(args.reader.resolve() if args.reader else build(cache))
    install = str(args.install.resolve())
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='casc-plan-', dir=cache) as work:
        inventory = Path(work) / 'inventory.tsv'
        subprocess.run([reader, 'inventory', install, str(inventory)], check=True)
        with inventory.open(encoding='utf8', newline='') as handle:
            selected = select_files(csv.DictReader(handle, delimiter='\t'), args.locale)
        with tempfile.TemporaryDirectory(prefix='.gamedata-', dir=out.parent) as temporary:
            tree = Path(temporary) / 'tree'
            tree.mkdir()
            plan = Path(work) / 'plan.tsv'
            plan.write_text(''.join(f'{src}\t{tree / dst}\n' for dst, src in selected.items()), encoding='utf8')
            subprocess.run([reader, 'extract', install, str(plan)], check=True)
            aliases = file_aliases(tree)
            b64, maps = write_indexes(tree, [*selected, *aliases])
            tree.rename(out)
        inventory.replace(cache / 'casc-inventory.tsv')
    print(f'{out}: {len(selected)} game files, {len(aliases)} legacy aliases, {maps} melee/scenario maps, {b64} base64 text sidecars')


if __name__ == '__main__':
    main()
