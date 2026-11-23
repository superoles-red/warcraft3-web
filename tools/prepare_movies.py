#!/usr/bin/env python3
"""Package the nine classic Warcraft III cinematics with an installed audio locale."""
import argparse
import concurrent.futures
import json
from pathlib import Path
import re
import subprocess
import tempfile

from build_casc_reader import build

NAMES = ('tutorialop', 'tutorialin', 'humanop', 'humaned', 'undeaded',
         'orced', 'nightelfed', 'introx', 'outrox')
PROJECT = Path(__file__).resolve().parents[1]


def probe(path):
    result = subprocess.run(['ffprobe', '-v', 'error', '-show_format', '-show_streams',
                             '-of', 'json', str(path)], check=True, capture_output=True)
    return json.loads(result.stdout)


def extract(install, locale, source, reader):
    lines = []
    for name in NAMES:
        lines.append(f'war3.w3mod:movies\\{name}.avi\t{source / (name + ".avi")}\n')
        audio = source / 'audio' / (name + '.mp3')
        lines.append(f'war3.w3mod:_locales\\{locale}.w3mod:movies\\audio\\{name}.mp3\t{audio}\n')
    plan = source / 'extract.tsv'
    plan.write_text(''.join(lines), encoding='utf8')
    subprocess.run([reader, 'extract', install, plan], check=True)


def package(source, destination, locale, name, compact):
    video = source / (name + '.avi')
    audio = source / 'audio' / (name + '.mp3')
    video_info = probe(video)
    picture = video_info['streams'][0]
    if not compact and picture['codec_name'] != 'vp9':
        raise ValueError(f'{video} needs the --compact profile to transcode {picture["codec_name"]}.')
    if compact:
        video_options = ['-vf', 'scale=min(640\\,iw):-2:flags=lanczos', '-pix_fmt', 'yuv420p',
                         '-c:v', 'libvpx-vp9', '-crf', '32', '-b:v', '0', '-row-mt', '1',
                         '-deadline', 'realtime', '-cpu-used', '8', '-threads:v', '3']
    else:
        video_options = ['-c:v', 'copy']
    suffix = '640' if compact else 'native'
    path = destination / f'{name}_{suffix}.webm'
    subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-i', video, '-i', audio,
                    '-map', '0:v:0', '-map', '1:a:0', *video_options, '-c:a', 'libopus', '-b:a', '80k',
                    '-metadata:s:a:0', f'language={locale[:2]}', '-f', 'webm', path], check=True)
    result = probe(path)
    codecs = [s['codec_name'] for s in result['streams']]
    if codecs != ['vp9', 'opus']:
        raise ValueError(f'{path}: unexpected codecs {codecs}')
    video_duration = float(video_info['format']['duration'])
    audio_duration = float(probe(audio)['format']['duration'])
    duration = float(result['format']['duration'])
    # Some sidecar soundtracks have trailing silence. Keep both streams intact.
    if abs(duration - max(audio_duration, video_duration)) > 2:
        raise ValueError(f'{path}: unexpected output duration {duration}')
    print(f'{name} {path.stat().st_size:,} bytes', flush=True)
    return dict(name=name, width=result['streams'][0]['width'], height=result['streams'][0]['height'],
                video_seconds=round(video_duration, 3), audio_seconds=round(audio_duration, 3),
                webm_seconds=round(duration, 3), source_video_bytes=video.stat().st_size,
                source_audio_bytes=audio.stat().st_size, webm_bytes=path.stat().st_size)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument('--install', type=Path, help='Directory containing Data/ and .build.info')
    src.add_argument('--source', type=Path, help='Previously extracted CASC movies/ with locale audio/ subdirectory')
    parser.add_argument('--locale', default='ruru', help='CASC locale (default ruRU)')
    parser.add_argument('--cache', type=Path, default=Path.home() / '.cache/warcraft3-original-web')
    parser.add_argument('--reader', type=Path, help='Previously compiled tools/casc_reader.cpp')
    parser.add_argument('--output', type=Path, default=PROJECT / 'local/movies', help='New output directory')
    parser.add_argument('--compact', action='store_true', help='Transcode picture to at most 640px, VP9 CRF 32')
    args = parser.parse_args()
    locale = args.locale.lower()
    if not re.fullmatch('[a-z]{4}', locale):
        parser.error('Expected a four-letter locale code.')
    out = args.output.resolve()
    if out.exists():
        parser.error(f'Output already exists: {out}. Choose a new directory.')
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out.parent, prefix='.cinematics-') as tmp:
        work = Path(tmp)
        source = args.source
        if args.install:
            source = work / 'source'
            source.mkdir()
            extract(args.install.resolve(), locale, source, args.reader or build(args.cache))
        destination = work / 'webm'
        destination.mkdir()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            items = list(pool.map(lambda n: package(source, destination, locale, n, args.compact), NAMES))
        report = dict(locale=locale, profile='compact' if args.compact else 'original-vp9', movies=items)
        (destination / 'sizes.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
        destination.rename(out)


if __name__ == '__main__':
    main()
