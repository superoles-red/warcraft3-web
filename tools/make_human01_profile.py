#!/usr/bin/env python3
"""Build a private ZIP for chapter one, The Defense of Strahnbrad, from local game data."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile

PROJECT = Path(__file__).resolve().parents[1]
CHAPTER = 'campaign/human01.w3m'
MAP_HASH = 'f8fc02e48c7ed6975951b6ecfadd6daa0294c0b5356a6bbc9aa1311f725d01ff'

# Four recordings are shared with chapter three but explicitly played by Human01.
BORROWED_VOICES = {'h03footman47', 'h03villagerm43', 'h03villagerm44', 'h03villagerm50'}
# The three thematic tracks are named in the map script. Include the human race
# playlist and the menu / victory / defeat music for transitions.
MUSIC = {'human1', 'human2', 'human3', 'humanvictory', 'humandefeat', 'mainscreen',
         'war3xmainscreen', 'comradeship', 'darkagents', 'heroicvictory', 'arthastheme'}
# Neutral actors from Human01's JASS, unit placements and custom unit parents.
# Scripted reinforcements belong to the human, orc, bandit and gnoll groups.
VOICED_FACTIONS = {'human', 'orc', 'critters'}
CREEP_BANKS = {'bandit', 'banditlord', 'banditmage', 'banditspearthrower',
               'gnoll', 'gnollarcher', 'gnollbrute', 'gnollking', 'gnollwarden'}


def chapter_resource(relative):
    parts = relative.parts
    name = relative.as_posix()
    if parts[0] in ('campaign', 'maps'):
        return name == CHAPTER
    if name.startswith('sound/dialogue/'):
        return (name.startswith('sound/dialogue/humancampaign/human01/') or
                (name.startswith('sound/dialogue/humancampaign/human03/') and relative.stem in BORROWED_VOICES))
    if name.startswith('sound/music/'):
        return relative.stem in MUSIC
    if name.startswith('sound/ambient/'):
        # Terrain type L in this map means Lordaeron Summer. The map also uses
        # water / door effects, while the campaign menu uses the root ambience.
        return len(parts) == 3 or parts[2] in ('lordaeronsummer', 'doodadeffects')
    # No unit placement, custom unit parent or scripted spawn in this mission
    # uses one of these three factions. Retain cross-referenced textures.
    if (parts[0] in {'units', 'buildings'} and len(parts) > 2 and
            parts[1] in {'nightelf', 'undead', 'naga'} and relative.suffix == '.mdx'):
        return False
    if parts[0] == 'units' and relative.suffix == '.wav' and len(parts) > 2:
        return (parts[1] in VOICED_FACTIONS or
                (parts[1] == 'creeps' and parts[2] in CREEP_BANKS) or
                (parts[1] == 'demon' and parts[2] == 'chaoswarlord'))
    # Keep every terrain texture, ability, icon, data table and remaining model.
    # This also covers alternate models, weather and triggered reinforcement spawns.
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--local', type=Path, default=PROJECT / 'local')
    parser.add_argument('--trace', type=Path, help='Add every local resource observed in an existing browser session')
    parser.add_argument('--output', type=Path, default=PROJECT / 'local/Warcraft-III-Human01-mobile.zip')
    args = parser.parse_args()
    data = args.local.resolve() / 'gamedata'
    chapter = data / CHAPTER
    if not chapter.is_file() or hashlib.sha256(chapter.read_bytes()).hexdigest() != MAP_HASH:
        parser.error('This chapter profile was verified against the original 1.31.1.12164 Human01 map.')
    names = {'gamedata/' + f.relative_to(data).as_posix() for f in data.rglob('*')
             if f.is_file() and chapter_resource(f.relative_to(data))}
    # Additional assets requested by the menu and its default two-player map
    # in our captured playtest, listed by path without embedding game content.
    startup = Path(__file__).with_name('human01-startup.txt')
    names.update(startup.read_text(encoding='utf8').splitlines())
    if args.trace:
        names.update(args.trace.read_text(encoding='utf8').splitlines())
    with tempfile.TemporaryDirectory() as tmp:
        manifest = Path(tmp) / 'human01.txt'
        manifest.write_text(''.join(f'{name}\n' for name in sorted(names)), encoding='utf8')
        subprocess.run([sys.executable, str(PROJECT / 'tools/make_pack.py'), args.output,
                        '--local', args.local, '--trace', manifest, '--start-map', CHAPTER], check=True)


if __name__ == '__main__':
    main()
