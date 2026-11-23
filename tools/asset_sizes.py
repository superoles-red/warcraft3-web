#!/usr/bin/env python3
"""Measure the installer and the local assets referenced by the game preparation profile."""
import argparse
import collections
import csv
import json
from pathlib import Path
import subprocess

from prepare_game import select_files


def category(path):
    suffix = Path(path).suffix
    if suffix == '.wav':
        return 'wav'
    if suffix == '.mp3':
        if '/music/' in path:
            return 'music_mp3'
        if '/dialogue/' in path:
            return 'dialogue_mp3'
        return 'other_mp3'
    if suffix in {'.blp', '.tga', '.png'}:
        return 'textures'
    if suffix == '.mdx':
        return 'models'
    if path.startswith('campaign/'):
        return 'campaign'
    if suffix in {'.w3m', '.w3x'}:
        return 'melee_and_other_maps'
    return 'other'


def installer_group(path):
    if path.startswith('app/Data/data/data.'):
        return 'CASC_payload'
    if path.startswith('app/Data/'):
        return 'CASC_indices_and_config'
    if path.startswith('app/Movies/'):
        return 'movie_video' if path.endswith('.avi') else 'movie_sound_all_variants'
    if path.startswith(('app/x86/', 'app/x86_64/')):
        return 'Windows_client_and_editor'
    return 'loose_files_demos_and_docs'


def measure(installer, inventory, locale):
    package = {p.name: p.stat().st_size for p in [installer, *sorted(installer.parent.glob('setup-*.bin'))]}
    listing = subprocess.check_output(['innoextract', '-s', '-l', '--list-sizes', '--collisions', 'rename',
                                       str(installer)], text=True)
    groups = collections.Counter()
    for line in listing.splitlines():
        size, name = line.split(' ', 1)
        groups[installer_group(name)] += int(size)
    with inventory.open(encoding='utf8', newline='') as handle:
        rows = list(csv.DictReader(handle, delimiter='\t'))
    selected = select_files(rows, locale)
    indexed = {r['path']: r for r in rows}
    sizes = collections.Counter()
    keyed = set()
    logical = 0
    for path, source in selected.items():
        record = indexed[source]
        size = int(record['bytes'])
        logical += size
        if record['ckey'] in keyed:
            continue
        keyed.add(record['ckey'])
        sizes[category(path)] += size
    return dict(installer=package, installer_bytes=sum(package.values()), expanded_bytes=dict(groups),
                expanded_all_variants_bytes=sum(groups.values()), casclib_named_paths=len(rows),
                casclib_local_paths=sum(r['local'] == '1' for r in rows),
                selected_locale=locale, selected_paths=len(selected), selected_bytes=logical,
                unique_casc_objects=len(keyed), selected_unique_bytes=dict(sizes),
                selected_total_unique_bytes=sum(sizes.values()))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('installer', type=Path)
    parser.add_argument('inventory', type=Path)
    parser.add_argument('--locale', default='ruru')
    args = parser.parse_args()
    print(json.dumps(measure(args.installer, args.inventory, args.locale), indent=2))
