#!/usr/bin/env python3
"""Compare compact cinematics to the prepared native WebM files, including timing and optional VMAF."""
import argparse
import json
from pathlib import Path
import statistics
import subprocess
import tempfile

from prepare_movies import NAMES, PROJECT, probe


def timestamps(path):
    text = subprocess.check_output([
        'ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'packet=pts',
        '-of', 'csv=p=0', path], text=True)
    # Both WebM files use Matroska's one-millisecond clock; check this in compare().
    return [int(t) for t in text.split()]


def audio_hash(path):
    value = subprocess.check_output([
        'ffmpeg', '-nostdin', '-v', 'error', '-i', path, '-map', '0:a:0', '-c', 'copy',
        '-f', 'hash', '-hash', 'sha256', '-'], text=True)
    return value.strip().removeprefix('SHA256=')


def vmaf(original, compact, width, height):
    with tempfile.TemporaryDirectory() as temporary:
        # Compare displayed frames by ordinal; timestamp fidelity is tested separately.
        # Every 48th frame covers the entire movie, including fades and scene changes.
        graph = (f'[0:v]settb=1/1000,setpts=N*40,setsar=1[ref];'
                 f'[1:v]scale={width}:{height}:flags=lanczos,settb=1/1000,setpts=N*40,setsar=1[test];'
                 '[test][ref]libvmaf=shortest=1:n_subsample=48:n_threads=2:log_fmt=json:log_path=scores.json')
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-filter_complex_threads', '1',
                        '-threads', '2', '-i', original.resolve(), '-threads', '2', '-i', compact.resolve(),
                        '-filter_complex', graph, '-an', '-enc_time_base', '1:1000',
                        '-fps_mode', 'passthrough', '-f', 'null', '-'], cwd=temporary, check=True)
        info = json.loads((Path(temporary) / 'scores.json').read_text())
    values = sorted(frame['metrics']['vmaf'] for frame in info['frames'])
    return dict(samples=len(values), mean=round(statistics.mean(values), 3),
                fifth_percentile=round(values[(len(values) - 1) // 20], 3))


def compare(original, compact, measure_quality=False):
    source = probe(original)
    result = probe(compact)
    output_codecs = [s['codec_name'] for s in result['streams']]
    if output_codecs != ['vp9', 'opus']:
        raise ValueError(f'{compact.name}: unexpected streams {output_codecs}')
    for media in (source, result):
        if media['streams'][0]['time_base'] != '1/1000':
            raise ValueError(f'{compact.name}: unexpected timestamp units')
    a, b = timestamps(original), timestamps(compact)
    if not a or len(a) != len(b):
        raise ValueError(f'{compact.name}: frame packet count changed from {len(a)} to {len(b)}')
    max_shift = max(abs(p - q) for p, q in zip(a, b))
    if max_shift > 10:
        raise ValueError(f'{compact.name}: frame moved by up to {max_shift} ms')
    delta = abs(float(result['format']['duration']) - float(source['format']['duration']))
    checksum = audio_hash(original)
    if delta > 0.02 or checksum != audio_hash(compact):
        raise ValueError(f'{compact.name}: duration or audio bitstream changed')
    row = dict(name=compact.name, native_bytes=original.stat().st_size, compact_bytes=compact.stat().st_size,
               frames=len(a), max_frame_shift_ms=max_shift, duration_difference_ms=round(delta*1000),
               audio_sha256=checksum)
    if measure_quality:
        row['vmaf'] = vmaf(original, compact, source['streams'][0]['width'], source['streams'][0]['height'])
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native', type=Path, default=PROJECT / 'local/movies')
    parser.add_argument('--compact', type=Path, default=PROJECT / 'local/compact/movies')
    parser.add_argument('--vmaf', action='store_true', help='FFmpeg with libvmaf; sample every 48th frame')
    args = parser.parse_args()
    reports = [compare(args.native / f'{name}_native.webm', args.compact / f'{name}_640.webm', args.vmaf)
               for name in NAMES]
    print(json.dumps(reports, indent=2))


if __name__ == '__main__':
    main()
